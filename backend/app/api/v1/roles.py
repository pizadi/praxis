"""Admin-defined roles: CRUD over the permission sets assigned to users."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_perm
from app.api.pagination import Page, clamp_limit_offset, paginate
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.permission_labels_fa import (
    PERMISSION_GROUP_LABELS_FA,
    PERMISSION_LABELS_FA,
)
from app.core.permissions import ALL_PERMISSIONS, PERMISSION_CATALOG
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Role, User
from app.schemas import RoleCreateIn, RoleOut, RoleUpdateIn
from app.services import audit

router = APIRouter(prefix="/roles", tags=["roles"])


async def _get_or_404(db: AsyncSession, role_id: int) -> Role:
    role = await db.scalar(
        select(Role).where(Role.id == role_id, Role.deleted_at.is_(None))
    )
    if role is None:
        raise NotFoundError("Role not found", code="role_not_found")
    return role


async def _live_user_count(db: AsyncSession, role_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role_id == role_id, User.deleted_at.is_(None))
        )
    )


@router.get("/permissions")
async def permission_catalog(
    _: User = Depends(require_perm("roles.manage")),
):
    """Grouped permission catalog for the roles UI."""
    return [
        {
            "group": PERMISSION_GROUP_LABELS_FA[group_id],
            "items": [
                {"key": key, "label": PERMISSION_LABELS_FA[key]} for key in permissions
            ],
        }
        for group_id, permissions in PERMISSION_CATALOG
    ]


@router.get("", response_model=Page[RoleOut])
async def list_roles(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("roles.manage")),
):
    stmt = select(Role).where(Role.deleted_at.is_(None)).order_by(Role.id)
    limit, offset = clamp_limit_offset(limit, offset)
    roles, total = await paginate(db, stmt, limit=limit, offset=offset)
    role_ids = [r.id for r in roles]
    counts: dict[int, int] = {}
    if role_ids:
        count_rows = (
            await db.execute(
                select(User.role_id, func.count())
                .where(
                    User.role_id.in_(role_ids),
                    User.deleted_at.is_(None),
                )
                .group_by(User.role_id)
            )
        ).all()
        counts = {int(role_id): int(count) for role_id, count in count_rows}
    items = []
    for r in roles:
        out = RoleOut.model_validate(r)
        out.user_count = counts.get(r.id, 0)
        items.append(out)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("roles.manage")),
):
    name = body.name.strip()
    if not name:
        raise BusinessRuleError("Name required", code="name_required")
    unknown = set(body.permissions) - ALL_PERMISSIONS
    if unknown:
        raise BusinessRuleError(
            f"Unknown permissions: {sorted(unknown)}", code="unknown_permissions"
        )
    exists = await db.scalar(
        select(Role).where(Role.name == name, Role.deleted_at.is_(None))
    )
    if exists:
        raise ConflictError("A role with this name already exists", code="role_name_taken")
    role = Role(
        name=name,
        is_system=False,
        permissions_json=RoleOut.json_sorted(body.permissions),
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.CREATE,
        entity_type="role",
        entity_id=role.id,
        summary=name,
        details={"permissions": body.permissions},
    )
    return role


@router.get("/{role_id}", response_model=RoleOut)
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("roles.manage")),
):
    role = await _get_or_404(db, role_id)
    out = RoleOut.model_validate(role)
    out.user_count = await _live_user_count(db, role.id)
    return out


@router.patch("/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: int,
    body: RoleUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("roles.manage")),
):
    role = await _get_or_404(db, role_id)
    if role.is_system and role.name == "admin":
        raise ConflictError(
            "The admin role cannot be modified", code="admin_role_locked"
        )
    before_perms = role.permissions
    before_name = role.name
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise BusinessRuleError("Name required", code="name_required")
        dup = await db.scalar(
            select(Role).where(
                Role.name == name,
                Role.deleted_at.is_(None),
                Role.id != role.id,
            )
        )
        if dup:
            raise ConflictError("A role with this name already exists", code="role_name_taken")
        role.name = name
    if body.permissions is not None:
        unknown = set(body.permissions) - ALL_PERMISSIONS
        if unknown:
            raise BusinessRuleError(
                f"Unknown permissions: {sorted(unknown)}", code="unknown_permissions"
            )
        role.permissions_json = RoleOut.json_sorted(body.permissions)
    await db.commit()
    await db.refresh(role)
    changed: dict = {}
    if before_name != role.name:
        changed["name"] = {"old": before_name, "new": role.name}
    if before_perms != role.permissions:
        removed = sorted(set(before_perms) - set(role.permissions))
        added = sorted(set(role.permissions) - set(before_perms))
        changed["permissions"] = {"removed": removed, "added": added}
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.UPDATE,
        entity_type="role",
        entity_id=role.id,
        summary=role.name,
        details=changed or None,
    )
    out = RoleOut.model_validate(role)
    out.user_count = await _live_user_count(db, role.id)
    return out


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("roles.manage")),
):
    role = await _get_or_404(db, role_id)
    if role.is_system:
        raise ConflictError("System roles cannot be deleted", code="system_role")
    in_use = await _live_user_count(db, role.id)
    if in_use:
        raise ConflictError(
            f"Role is assigned to {in_use} user(s); reassign them first",
            code="role_in_use",
        )
    role.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.DELETE,
        entity_type="role",
        entity_id=role.id,
        summary=role.name,
    )
    return None
