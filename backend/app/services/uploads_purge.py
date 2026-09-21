"""Automatic uploads-directory purge: remove orphaned files.

An orphan is a file in UPLOAD_DIR that is referenced by no attachment row
(live or soft-deleted — deleted rows still own their file until a trash
purge). Only files matching the app's storage-name pattern (UUID hex +
sanitized extension, see api/deps.save_upload) are ever considered: foreign
files that nobody knows about are left alone rather than guessed at.

A grace period (file mtime) protects in-flight uploads — a file is written
to disk before its attachment row commits — and the post-import merge
window (files restored from a tarball the DB hasn't caught up with).

The sweeper runs once at API startup and then periodically from the app
lifespan; each pass that removes anything is recorded in the audit trail
as the system user. No user interaction.
"""

import asyncio
import datetime as dt
import logging
import os
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Attachment
from app.services import audit

log = logging.getLogger("clinic.uploads")

STORAGE_NAME_RE = re.compile(r"^[0-9a-f]{32}(\.[A-Za-z0-9]{1,16})?$")

GRACE_SECONDS = 24 * 3600
INTERVAL_SECONDS = 6 * 3600


async def purge_once(db: AsyncSession, now: dt.datetime | None = None) -> dict:
    """One sweep: unlink unreferenced, pattern-matching, older-than-grace
    files; returns a summary. Never raises (failures are logged)."""
    now = now or dt.datetime.now()
    cutoff = now.timestamp() - GRACE_SECONDS
    removed = 0
    removed_bytes = 0
    try:
        referenced: set[str] = {
            s
            for s in (await db.scalars(select(Attachment.stored_filename))).all()
            if s is not None
        }
        root = os.path.abspath(settings.upload_dir)
        if os.path.isdir(root):
            for dirpath, dirnames, filenames in os.walk(root):
                # hidden dirs are runtime staging (e.g. .import-*) — skipped
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for name in filenames:
                    if name in referenced or not STORAGE_NAME_RE.match(name):
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        if os.stat(path).st_mtime > cutoff:
                            continue  # too young — an upload may be in flight
                        size = os.stat(path).st_size
                        os.unlink(path)
                    except OSError:
                        log.warning("uploads purge: could not remove %s", path)
                        continue
                    removed += 1
                    removed_bytes += size
        summary = {"removed": removed, "removed_bytes": removed_bytes}
        if removed:
            await audit.log_action(
                db,
                user=None,
                request=None,
                action=audit.DELETE,
                entity_type="uploads_purge",
                summary=f"removed {removed} orphaned file(s)",
                details=summary,
            )
        return summary
    except Exception:  # noqa: BLE001 — maintenance must never crash the app
        log.exception("uploads purge failed")
        return {"removed": 0, "removed_bytes": 0}


async def purge_loop() -> None:
    """Startup sweep + periodic sweeper (runs for the process lifetime)."""
    while True:
        from app.db.session import SessionLocal

        async with SessionLocal() as session:
            s = await purge_once(session)
            if s["removed"]:
                log.info("uploads purge: %s", s)
        await asyncio.sleep(INTERVAL_SECONDS)
