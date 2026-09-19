import datetime as dt
import mimetypes
import os
import re
import uuid
from pathlib import Path

import jwt
from fastapi import Depends, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import decode_token
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import RefreshToken, User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = decode_token(token, "access")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None
    stmt = select(User).where(User.id == user_id).options(selectinload(User.role))
    user = await db.scalar(stmt)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User inactive or gone")
    return user


def require_perm(*perms: str):
    """Dependency factory: allow if the user has ANY of the given permissions."""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if not user.has_perm(*perms):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


require_admin = require_perm("users.manage")


# --- File storage helpers -----------------------------------------------------


def upload_dir() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_storage_name(original: str) -> str:
    """UUID-based storage name; extension sanitized, never client-controlled."""
    ext = Path(original).suffix
    ext = _SAFE_NAME.sub("", ext)[:16]
    return f"{uuid.uuid4().hex}{ext}"


def resolve_stored_path(stored_filename: str) -> Path:
    """Resolve a stored filename to an absolute path inside UPLOAD_DIR only.

    Hardening: reject separators / traversal and verify containment with
    Path.resolve() — never trust startswith checks.
    """
    if stored_filename != os.path.basename(stored_filename) or stored_filename in (
        ".",
        "..",
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    root = upload_dir().resolve()
    candidate = (root / stored_filename).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    return candidate


async def save_upload_stream(file: UploadFile, original_name: str) -> dict:
    """Stream an uploaded file to UPLOAD_DIR, enforcing the size cap while
    reading — the request body is never fully buffered in memory (a 200 MB
    upload against a 50 MB cap rejects after ~50 MB, not after 200 MB)."""
    stored = safe_storage_name(original_name)
    path = upload_dir() / stored
    size = 0
    try:
        with path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large"
                    )
                out.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)  # never leave partial files behind
        raise
    if size == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty file")
    return {
        "stored_filename": stored,
        "original_filename": original_name[:255],
        "mime_type": (mimetypes.guess_type(original_name)[0] or "application/octet-stream"),
        "size_bytes": size,
    }


def delete_stored_file(stored_filename: str | None) -> None:
    """Best-effort physical deletion; DB cleanup proceeds regardless."""
    if not stored_filename:
        return
    try:
        path = resolve_stored_path(stored_filename)
        path.unlink(missing_ok=True)
    except Exception:
        pass


# --- Refresh-token helpers ----------------------------------------------------


async def issue_refresh_token(db: AsyncSession, user: User) -> str:
    from app.core.security import create_refresh_token

    token = create_refresh_token(user.id)
    payload = decode_token(token, "refresh")
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=payload["jti"],
            expires_at=dt.datetime.fromtimestamp(payload["exp"], dt.UTC),
        )
    )
    await db.commit()
    return token


async def rotate_refresh_token(db: AsyncSession, raw_token: str) -> User:
    payload = decode_token(raw_token, "refresh")
    jti = payload.get("jti")
    row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    now = utc_now()
    if row is None:
        raise invalid
    expires_at = _as_utc(row.expires_at)
    if row.revoked_at is not None or expires_at is None or expires_at < now:
        raise invalid
    row.revoked_at = now
    user = await db.scalar(select(User).where(User.id == row.user_id))
    if user is None or not user.is_active:
        raise invalid
    await db.commit()
    return user


def _as_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value


async def revoke_user_tokens(db: AsyncSession, user_id: int) -> None:
    """Used on logout-all / user deactivation to kill refresh tokens."""
    from sqlalchemy import update

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    await db.commit()
