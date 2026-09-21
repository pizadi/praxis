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
MERGE = "merge"  # taxonomy merge (rename onto an existing name)
LOGIN = "login"  # reserved; login attempts live in login_audit
LOGOUT = "logout"  # refresh-token revocation at session end


def _client_ip(request: Request) -> str:
    """Best-effort real client IP.

    The API sits behind the nginx reverse proxy (and, on LAN deployments,
    possibly another hop), so request.client.host is the last proxy's
    address — useless in the audit trail. nginx sets X-Real-IP and
    X-Forwarded-For ($proxy_add_x_forwarded_for); the leftmost XFF entry is
    the original client. Direct (non-proxied) access has no such headers
    and falls back to the peer address.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first[:64]
    real = request.headers.get("x-real-ip")
    if real and real.strip():
        return real.strip()[:64]
    return (request.client.host if request.client else "")[:64]


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
                ip_address=_client_ip(request) if request is not None else "",
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
