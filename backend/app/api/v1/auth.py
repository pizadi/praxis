import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, issue_refresh_token, rotate_refresh_token
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import LoginAudit, RefreshToken, User
from app.schemas import LoginIn, RefreshIn, TokenPair, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens_for(user: User, refresh: str) -> TokenPair:
    access = create_access_token(user.id, user.role.value)
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


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(User).where(User.username == body.username, User.deleted_at.is_(None))
    )
    ok = user is not None and user.is_active and verify_password(body.password, user.password_hash)
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
async def logout(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    """Revoke a single refresh token (rotation already revokes previous)."""
    try:
        payload = jwt.decode(
            body.refresh_token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from None
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == payload.get("jti"))
        .values(revoked_at=utc_now())
    )
    await db.commit()
    return None


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
