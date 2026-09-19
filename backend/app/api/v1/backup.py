"""Admin backup: tarball the database + uploaded files for download.

The API container has no pg_dump binary, so the database is dumped via
psycopg2 `COPY ... TO STDOUT` (fast, server-side). Each table is copied
into a SpooledTemporaryFile (spills to disk, never RAM-bound) and then
added to a streaming tar.gz together with the uploads volume — a large
uploads directory is never held in memory. Restore: create an empty DB,
run `alembic upgrade head`, then load each db/<table>.copy with
`psql -c "COPY <table> FROM STDIN"` (FK order), and unpack uploads/ into
UPLOAD_DIR. SQLite (dev) databases are archived as the raw file.

Import (upload a tarball back) lives in services/backup_import.py and its
endpoints at the bottom of this file. Backup and import share one job lock
(only one runs at a time).
"""

import contextlib
import datetime as dt
import json
import logging
import os
import tarfile
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import require_perm
from app.core.config import settings
from app.core.errors import BusinessRuleError, ConflictError
from app.core.tokens import utc_now
from app.db.session import APP_TZ, get_db
from app.models import User
from app.services import audit
from app.services.backup_import import (
    SUPPORTED_SCHEMA_VERSION,
    import_status,
    import_status_update,
    read_manifest,
    run_import,
)
from app.services.backup_state import DUMP_TABLES, JOB_LOCK, psycopg2_url

router = APIRouter(prefix="/admin/backup", tags=["backup"])

_status_lock = threading.Lock()
_status: dict = {"status": "idle", "started_at": None, "finished_at": None, "error": None}
_file_path: str | None = None


def _backup_state() -> dict:
    with _status_lock:
        st = dict(_status)
        if _status["status"] == "ready" and _file_path and os.path.exists(_file_path):
            st["size_bytes"] = os.path.getsize(_file_path)
        else:
            st["size_bytes"] = None
            if _status["status"] == "ready":
                _status.update(status="idle", finished_at=None)
        return st


def _dump_postgres(tar: tarfile.TarFile, manifest: dict) -> None:
    import psycopg2

    conn = psycopg2.connect(psycopg2_url())
    try:
        with conn.cursor() as cur:
            # REPEATABLE READ snapshot so all tables are consistent mid-job
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            for table in DUMP_TABLES:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table,),
                )
                if cur.fetchone()[0] == 0:
                    continue
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
                    (table,),
                )
                manifest["table_columns"][table] = [r[0] for r in cur.fetchall()]
                cur.execute(f'SELECT COUNT(*) FROM "{table}"')  # noqa: S608 — fixed names
                manifest["tables"][table] = cur.fetchone()[0]

                with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as buf:
                    cur.copy_expert(f'COPY "{table}" TO STDOUT', buf)  # noqa: S608 — fixed names
                    info = tarfile.TarInfo(name=f"db/{table}.copy")
                    info.size = buf.tell()
                    buf.seek(0)
                    tar.addfile(info, buf)
        conn.rollback()
    finally:
        conn.close()


def _dump_sqlite(tar: tarfile.TarFile, manifest: dict) -> None:
    import sqlite3

    db_file = settings.database_url.split("///", 1)[-1]
    if not os.path.exists(db_file):
        manifest["tables"]["__sqlite_file__"] = None
        return
    manifest["tables"]["__sqlite_file__"] = db_file
    con = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        tables = [
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r[0].startswith("sqlite_")
        ]
        for t in tables:
            manifest["table_columns"][t] = [
                r[1] for r in con.execute(f"PRAGMA table_info(\"{t}\")").fetchall()  # noqa: S608
            ]
            manifest["tables"][t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]  # noqa: S608
    finally:
        con.close()
    tar.add(db_file, arcname="db/clinic.sqlite3")


def _run_backup() -> None:
    from app import __version__

    manifest: dict = {
        "created_at": utc_now().isoformat(),
        "schema_version": 2,
        "app_version": __version__,
        "app_timezone": settings.app_timezone,
        "tables": {},
        "table_columns": {},
        "restore": (
            "1) create an empty DB and run `alembic upgrade head` "
            "2) for each db/<table>.copy (FK order): "
            'psql -c "COPY <table> (cols...) FROM STDIN" < db/<table>.copy '
            "3) unpack uploads/ into UPLOAD_DIR — or use the in-app import "
            "(POST /admin/backup/import), which is transactional"
        ),
    }
    path: str | None = None
    try:
        fd, path = tempfile.mkstemp(prefix="clinic-backup-", suffix=".tar.gz")
        os.close(fd)
        with tarfile.open(path, "w:gz") as tar:
            if settings.database_url.startswith("postgres"):
                _dump_postgres(tar, manifest)
            else:
                _dump_sqlite(tar, manifest)

            # uploaded patient files (streamed; the dir may be large).
            # dot-dirs are runtime staging (e.g. .import-*) — never archived
            upload_dir = Path(settings.upload_dir)
            if upload_dir.is_dir():
                n_files = 0
                for f in sorted(upload_dir.rglob("*")):
                    if f.is_file() and not f.parent.name.startswith("."):
                        tar.add(f, arcname=f"uploads/{f.relative_to(upload_dir)}")
                        n_files += 1
                manifest["uploads_files"] = n_files

            m = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(m)
            from io import BytesIO

            tar.addfile(info, BytesIO(m))

        with _status_lock:
            global _file_path
            _file_path = path
            path = None
            _status.update(status="ready", started_at=None, finished_at=utc_now(), error=None)
    except Exception as exc:  # noqa: BLE001 — the job thread must never crash loudly
        logging.getLogger("clinic.backup").exception("backup failed")
        with _status_lock:
            _status.update(status="error", started_at=None, finished_at=utc_now(), error=str(exc))
        if path and os.path.exists(path):
            with contextlib.suppress(OSError):
                os.unlink(path)
    finally:
        JOB_LOCK.release()


def _start_job() -> bool:
    global _file_path
    if not JOB_LOCK.acquire(blocking=False):
        return False
    with _status_lock:
        if _status["status"] == "running":
            JOB_LOCK.release()
            return False
        if any(t.name == "clinic-backup" and t.is_alive() for t in threading.enumerate()):
            _status.update(status="running")
            JOB_LOCK.release()
            return False
        _status.update(status="running", started_at=utc_now(), finished_at=None, error=None)
        threading.Thread(target=_run_backup, name="clinic-backup", daemon=True).start()
        return True


@router.post("", status_code=202)
async def start_backup(
    db=Depends(get_db),
    user: User = Depends(require_perm("backup.manage")),
):
    if not _start_job():
        raise ConflictError("A backup is already running", code="backup_running")
    await audit.log_action(
        db,
        user=user,
        request=None,
        action=audit.CREATE,
        entity_type="backup",
        summary="backup started",
    )
    return {"status": "running"}


@router.get("")
async def backup_status(_: User = Depends(require_perm("backup.manage"))):
    return _backup_state()


@router.get("/download")
async def download_backup(_: User = Depends(require_perm("backup.manage"))):
    st = _backup_state()
    if st["status"] != "ready" or not _file_path:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No ready backup file")
    name = "clinic-backup-" + dt.datetime.now(APP_TZ).strftime("%Y%m%d-%H%M") + ".tar.gz"
    return FileResponse(_file_path, media_type="application/gzip", filename=name)


@router.delete("", status_code=204)
async def discard_backup(
    db=Depends(get_db),
    user: User = Depends(require_perm("backup.manage")),
):
    global _file_path
    with _status_lock:
        if _status["status"] == "running":
            raise ConflictError("A backup is running", code="backup_running")
        if _file_path and os.path.exists(_file_path):
            os.unlink(_file_path)
        _file_path = None
        _status.update(status="idle", started_at=None, finished_at=None, error=None)
    await audit.log_action(
        db,
        user=user,
        request=None,
        action=audit.DELETE,
        entity_type="backup",
        summary="backup file discarded",
    )
    return None


# --- import (restore from a tarball) ---------------------------------------------


@router.get("/import")
async def import_status_endpoint(_: User = Depends(require_perm("backup.manage"))):
    return import_status()


@router.post("/import", status_code=202)
async def import_backup(
    request: Request,
    file: UploadFile = File(...),
    force: bool = Form(False),
    db=Depends(get_db),
    user: User = Depends(require_perm("backup.manage")),
):
    """Restore DB + uploads from a backup tarball (see services/backup_import.py).

    Version handling: older tarball versions import via the manifest's
    column lists; a NEWER app_version refuses with 409 `newer_version`
    unless force=true — and even then any unresolvable error rolls the
    whole import back.
    """
    if not JOB_LOCK.acquire(blocking=False):
        raise ConflictError("A backup or import job is already running", code="backup_running")
    started = False
    try:
        # spool the upload to a temp file the worker thread can re-open
        fd, tar_path = tempfile.mkstemp(prefix="clinic-import-", suffix=".tar.gz")
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        try:
            manifest = read_manifest(tar_path)
        except Exception as exc:
            with contextlib.suppress(OSError):
                os.unlink(tar_path)
            raise BusinessRuleError(
                f"Invalid backup tarball: {exc}", code="invalid_backup"
            ) from None

        newer = import_version_gate(manifest, force)
        if newer is not None:
            os.unlink(tar_path)
            raise newer  # 409 newer_version carrying the manifest summary

        import_status_update("importing", summary=None, error=None)
        threading.Thread(
            target=_run_import_job,
            args=(tar_path, manifest.get("app_version"), force),
            name="clinic-import",
            daemon=True,
        ).start()
        started = True
    finally:
        if not started:
            JOB_LOCK.release()  # the worker releases it on success
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.CREATE,
        entity_type="backup_import",
        summary=f"import started (app_version={manifest.get('app_version', '?')}, force={force})",
        details={
            "app_version": manifest.get("app_version"),
            "schema_version": manifest.get("schema_version", 1),
            "forced": force,
        },
    )
    return {"status": "importing"}


def import_version_gate(manifest: dict, force: bool) -> Exception | None:
    """Return the error to raise: 422 for an unsupported schema version,
    409 `newer_version` when the producer is newer (unless forced)."""
    sv = manifest.get("schema_version", 1)
    if sv > SUPPORTED_SCHEMA_VERSION:
        return BusinessRuleError(
            f"Backup schema_version {sv} is newer than supported "
            f"({SUPPORTED_SCHEMA_VERSION})",
            code="unsupported_schema",
        )
    from packaging.version import Version

    from app import __version__

    producer = manifest.get("app_version")
    if producer and not force:
        try:
            if Version(producer) > Version(__version__):
                return ConflictError(
                    "این فایل پشتیبان با نسخهٔ جدیدتری از سامانه ساخته شده است",
                    code="newer_version",
                    details={
                        "tarball_app_version": producer,
                        "current_app_version": __version__,
                        "tables": manifest.get("tables", {}),
                    },
                )
        except Exception:
            pass  # unparsable producer version → let the import try
    return None


def _run_import_job(tar_path: str, producer_version: str | None, forced: bool) -> None:
    try:
        summary = run_import(tar_path)
        import_status_update("done", summary=summary, error=None)
        logging.getLogger("clinic.backup").info("import finished: %s", summary)
    except Exception as exc:  # noqa: BLE001 — the job thread must never crash loudly
        logging.getLogger("clinic.backup").exception("import failed")
        import_status_update("error", summary=None, error=str(exc))
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tar_path)
        JOB_LOCK.release()
