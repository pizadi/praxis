"""Audit trail service: records who did what, to what, when, from where."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

# actions
CREATE = "create"
UPDATE = "update"
DELETE = "delete"
RESTORE = "restore"
PURGE = "purge"
LOGIN = "login"  # reserved; login attempts live in login_audit
LOGOUT = "logout"  # refresh-token revocation at session end


async def log_action(
    db: AsyncSession,
    *,
    user: User | None,
    request: Request | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    summary: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Append one audit row. Never raises — auditing must not break the request."""
    try:
        db.add(
            AuditLog(
                user_id=user.id if user is not None else None,
                username=user.username if user is not None else "system",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary[:255],
                details=json.dumps(details, ensure_ascii=False) if details else None,
                ip_address=(
                    request.client.host if request is not None and request.client else ""
                )[:64],
            )
        )
        await db.commit()
    except Exception:  # pragma: no cover — audit failures must never bubble up
        import logging

        logging.getLogger("clinic.audit").exception("audit write failed")
        await db.rollback()


def diff_details(
    before: dict[str, Any], after: dict[str, Any], fields: list[str]
) -> dict[str, Any]:
    """Build a {field: {"old": x, "new": y}} payload for update audits."""
    changed: dict[str, Any] = {}
    for f in fields:
        if f in after and after[f] != before.get(f):
            changed[f] = {"old": before.get(f), "new": after[f]}
    return changed
