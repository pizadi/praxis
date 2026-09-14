"""Audit trail viewing (admin only). Writes happen via services.audit."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.pagination import Page, clamp_limit_offset, paginate
from app.db.session import get_db
from app.models import AuditLog, User
from app.schemas import AuditEntryOut

router = APIRouter(prefix="/admin/audit", tags=["audit"])


@router.get("", response_model=Page[AuditEntryOut])
async def list_audit(
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    username: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if username:
        stmt = stmt.where(AuditLog.username.ilike(f"%{username}%"))
    limit, offset = clamp_limit_offset(limit, offset)
    items, total = await paginate(db, stmt, limit=limit, offset=offset)
    return Page(
        items=[AuditEntryOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )
