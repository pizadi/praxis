import datetime as dt
import secrets

import jwt
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, issue_refresh_token, rotate_refresh_token
from app.core.client_ip import client_ip
from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError, RateLimitedError
from app.core.security import create_access_token, pwd_context, verify_password
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import LoginAudit, RefreshToken, User
from app.schemas import LoginIn, TokenPair, UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "praxis_refresh"
CSRF_COOKIE = "praxis_csrf"
SESSION_COOKIE_PATH = "/api/v1/auth"

# Verifying a throwaway hash for unknown usernames keeps the response time in
# the same range as the known-user path (argon2 verify dominates), so login
# timing cannot be used to enumerate usernames.
_DUMMY_PASSWORD_HASH = pwd_context.hash("timing-equalizer-dummy")


def _access_for(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def _set_session_cookies(response: Response, refresh: str) -> None:
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=max_age,
        path=SESSION_COOKIE_PATH,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=max_age,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="strict",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=SESSION_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")


def _validate_csrf(request: Request, token: str | None) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    if not token or not cookie_token or not secrets.compare_digest(token, cookie_token):
        raise AuthorizationError("Invalid CSRF token", code="csrf_failed")


async def _audit(db: AsyncSession, request: Request, username: str, success: bool) -> None:
    db.add(
        LoginAudit(
            username=username[:64],
            success=success,
            ip_address=client_ip(request),
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
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
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
        raise AuthenticationError("Invalid credentials", code="invalid_credentials")
    refresh = await issue_refresh_token(db, user)
    _set_session_cookies(response, refresh)
    return _access_for(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    request: Request,
    response: Response,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: AsyncSession = Depends(get_db),
):
    _validate_csrf(request, csrf_token)
    raw_refresh = request.cookies.get(REFRESH_COOKIE, "")
    if not raw_refresh:
        _clear_session_cookies(response)
        raise AuthenticationError("Invalid refresh token", code="invalid_refresh_token")
    try:
        user = await rotate_refresh_token(db, raw_refresh)
    except (jwt.InvalidTokenError, AuthenticationError):
        _clear_session_cookies(response)
        raise AuthenticationError(
            "Invalid refresh token", code="invalid_refresh_token"
        ) from None
    new_refresh = await issue_refresh_token(db, user)
    _set_session_cookies(response, new_refresh)
    return _access_for(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the refresh cookie and clear the browser session cookies."""
    _validate_csrf(request, csrf_token)
    raw_refresh = request.cookies.get(REFRESH_COOKIE, "")
    if not raw_refresh:
        _clear_session_cookies(response)
        raise AuthenticationError("Invalid refresh token", code="invalid_refresh_token")
    try:
        payload = jwt.decode(
            raw_refresh, settings.secret_key, algorithms=[settings.algorithm]
        )
    except jwt.InvalidTokenError:
        _clear_session_cookies(response)
        raise AuthenticationError(
            "Invalid refresh token", code="invalid_refresh_token"
        ) from None
    if payload.get("type") != "refresh":
        _clear_session_cookies(response)
        raise AuthenticationError("Invalid refresh token", code="invalid_refresh_token")

    row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == payload.get("jti")))
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == payload.get("jti"))
        .values(revoked_at=utc_now())
    )
    await db.commit()
    actor = await db.get(User, row.user_id) if row is not None else None
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.LOGOUT,
        entity_type="session",
        summary=(actor.username if actor is not None else "unknown refresh token"),
    )
    _clear_session_cookies(response)
    return None


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
