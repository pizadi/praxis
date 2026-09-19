from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_admin, revoke_user_tokens
from app.api.pagination import Page, paginate
from app.core.errors import ConflictError
from app.core.security import hash_password
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Role, User
from app.schemas import UserCreateIn, UserOut, UserUpdateIn
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


async def _get_or_404(db: AsyncSession, user_id: int) -> User:
    stmt = (
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .options(selectinload(User.role))
    )
    user = await db.scalar(stmt)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("", response_model=Page[UserOut])
async def list_users(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = (
        select(User)
        .where(User.deleted_at.is_(None))
        .options(selectinload(User.role))
        .order_by(User.id)
    )
    items, total = await paginate(db, stmt, limit=limit, offset=offset)
    return Page(
        items=[UserOut.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    exists = await db.scalar(
        select(User).where(
            User.username == body.username, User.deleted_at.is_(None)
        )
    )
    if exists:
        raise ConflictError("Username already taken", code="username_taken")
    role = await db.get(Role, body.role_id)
    if role is None or role.deleted_at is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Role not found")
    user = User(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role_id=body.role_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user, ["role"])
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.CREATE,
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.username} ({user.role_name})",
    )
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    return await _get_or_404(db, user_id)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = await _get_or_404(db, user_id)
    before: dict[str, Any] = {}
    if body.full_name is not None:
        before["full_name"] = user.full_name
    if body.role_id is not None:
        before["role_name"] = user.role_name
    if body.is_active is not None:
        before["is_active"] = user.is_active
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role_id is not None and body.role_id != user.role_id:
        role = await db.get(Role, body.role_id)
        if role is None or role.deleted_at is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Role not found")
        user.role_id = body.role_id
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    # kill outstanding refresh tokens when the credential changes or the
    # account is deactivated — access tokens are covered by the per-request
    # is_active check, refresh tokens must not outlive the change
    if body.password is not None or body.is_active is False:
        await revoke_user_tokens(db, user.id)
    await db.commit()
    await db.refresh(user, ["role"])
    after_fields = {f: getattr(user, f) for f in before}
    after_fields["role_name"] = user.role_name
    changed = audit.diff_details(before, after_fields, list(after_fields))
    if body.password is not None:
        changed["password"] = {"old": "•", "new": "•"}
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.UPDATE,
        entity_type="user",
        entity_id=user.id,
        summary=user.username,
        details=changed or None,
    )
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_admin),
):
    """Soft delete a user; also deactivate + revoke refresh tokens so a
    deleted user cannot log in while in the trash."""
    user = await _get_or_404(db, user_id)
    if user.id == current.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot delete yourself")
    # refuse deleting the last live admin (the system 'admin' role)
    if user.role.is_system and user.role.name == "admin":
        admins = (
            await db.scalars(
                select(User).where(
                    User.role_id == user.role_id,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
        ).all()
        if len(admins) <= 1:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot delete the last admin"
            )
    user.deleted_at = utc_now()
    user.is_active = False
    await revoke_user_tokens(db, user.id)
    await db.commit()
    await audit.log_action(
        db,
        user=current,
        request=request,
        action=audit.DELETE,
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.username} ({user.role_name})",
    )
    return None
