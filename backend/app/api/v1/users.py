from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.pagination import Page, paginate
from app.core.enums import UserRole
from app.core.errors import ConflictError
from app.core.security import hash_password
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import User
from app.schemas import UserCreateIn, UserOut, UserUpdateIn
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


async def _get_or_404(db: AsyncSession, user_id: int) -> User:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
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
    user = User(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.CREATE,
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.username} ({user.role.value})",
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
    before = {
        f: getattr(user, f)
        for f in ("full_name", "role", "is_active")
        if getattr(body, f) is not None
    }
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    await db.commit()
    await db.refresh(user)
    changed = audit.diff_details(before, {f: getattr(user, f) for f in before}, list(before))
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
    # refuse deleting the last live admin
    admins = (
        await db.scalars(
            select(User).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).all()
    if user.role == UserRole.ADMIN and len(admins) <= 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot delete the last admin"
        )
    from app.api.deps import revoke_user_tokens

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
        summary=f"{user.username} ({user.role.value})",
    )
    return None
