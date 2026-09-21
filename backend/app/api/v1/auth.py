import datetime as dt

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, issue_refresh_token, rotate_refresh_token
from app.core.config import settings
from app.core.errors import RateLimitedError
from app.core.security import create_access_token, pwd_context, verify_password
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import LoginAudit, RefreshToken, User
from app.schemas import LoginIn, RefreshIn, TokenPair, UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

# Verifying a throwaway hash for unknown usernames keeps the response time in
# the same range as the known-user path (argon2 verify dominates), so login
# timing cannot be used to enumerate usernames.
_DUMMY_PASSWORD_HASH = pwd_context.hash("timing-equalizer-dummy")


def _tokens_for(user: User, refresh: str) -> TokenPair:
    access = create_access_token(user.id)
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def _audit(db: AsyncSession, request: Request, username: str, success: bool) -> None:
    db.add(
        LoginAudit(
            username=username[:64],
            success=success,
            ip_address=(request.client.host if request.client else "")[:64],
        )
    )
    await db.commit()


async def _login_locked(db: AsyncSession, username: str) -> bool:
    """True when this username accumulated too many failed logins recently.

    Deliberately per-username, NOT per-IP: behind the nginx proxy every
    request shares the proxy address, so IP-based counting would let one
    attacker lock out all users.
    """
    since = utc_now() - dt.timedelta(minutes=settings.login_lock_minutes)
    failures = await db.scalar(
        select(func.count())
        .select_from(LoginAudit)
        .where(
            LoginAudit.username == username[:64],
            LoginAudit.success.is_(False),
            LoginAudit.created_at >= since,
        )
    )
    return (failures or 0) >= settings.login_max_failures


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    if await _login_locked(db, body.username):
        raise RateLimitedError(
            "Too many failed logins; try again later.", code="login_locked"
        )
    user = await db.scalar(
        select(User).where(User.username == body.username, User.deleted_at.is_(None))
    )
    ok = user is not None and user.is_active and verify_password(body.password, user.password_hash)
    if user is None:
        # same CPU work as the known-user path — no timing side channel
        verify_password(body.password, _DUMMY_PASSWORD_HASH)
    await _audit(db, request, body.username, ok)
    if not ok or user is None:
        # Deliberately identical error for unknown user and wrong password.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    refresh = await issue_refresh_token(db, user)
    return _tokens_for(user, refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    try:
        user = await rotate_refresh_token(db, body.refresh_token)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from None
    new_refresh = await issue_refresh_token(db, user)
    return _tokens_for(user, new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Revoke a single refresh token (rotation already revokes previous)."""
    try:
        payload = jwt.decode(
            body.refresh_token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from None
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == payload.get("jti")))
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == payload.get("jti"))
        .values(revoked_at=utc_now())
    )
    await db.commit()
    # audit the session end (user attributed via the revoked token's owner)
    actor = await db.get(User, row.user_id) if row is not None else None
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.LOGOUT,
        entity_type="session",
        summary=(actor.username if actor is not None else "unknown refresh token"),
    )
    return None


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
