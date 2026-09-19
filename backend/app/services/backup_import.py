"""Restore DB + uploads from a backup tarball (upload-side of backup.py).

Tarball layout (schema_version 2):
    manifest.json          — {"schema_version": 2, "app_version": "1.2.0",
                              "table_columns": {table: [cols...]}, ...}
    db/<table>.copy        — PostgreSQL COPY data (one file per table), or
    db/clinic.sqlite3      — SQLite (dev): the raw database file
    uploads/<name>         — the uploaded patient files (flat or nested)

Import semantics:
- PostgreSQL: ONE transaction — TRUNCATE every domain table, then COPY each
  dumped table (manifest column order; dump columns missing from the live
  schema are dropped, schema columns missing from the dump take defaults).
  Any error → full ROLLBACK, the running system is untouched. Serial
  sequences are re-synced from max(id) afterwards (still in-transaction).
- SQLite (dev/tests): ATTACH the archived database and copy table-by-table
  in one transaction; column lists come from the attached file itself, so
  even schema-less legacy manifests work.
- uploads/: extracted into UPLOAD_DIR/.import-<ts>/ staging and moved into
  place after the DB commit (merge — files not in the tarball stay; the
  periodic uploads-purge reclaims them after the grace period).

Version rules (enforced in the API layer):
- schema_version newer than SUPPORTED_SCHEMA_VERSION → refuse (422).
- producer app_version newer than the running app → refuse (409) unless
  the user explicitly forces the import; even forced, an unresolvable
  error rolls everything back.
"""

import contextlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.backup_state import DUMP_TABLES

SUPPORTED_SCHEMA_VERSION = 2

# hard caps for hostile/buggy tarballs (admins upload, but still)
MAX_MEMBER_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB per member
MAX_MEMBERS = 200_000

_status_lock = threading.Lock()
_status: dict = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "summary": None,
}


def import_status() -> dict:
    with _status_lock:
        return dict(_status)


def import_status_update(status: str, summary: dict | None, error: str | None) -> None:
    with _status_lock:
        _status.update(
            status=status,
            finished_at=None if status == "importing" else _status.get("finished_at"),
            error=error,
            summary=summary,
        )


def read_manifest(path: str) -> dict:
    """Validate the tarball's structure and return its manifest.

    Only manifest.json / db/... / uploads/... members are allowed; links and
    device nodes are rejected (zip-slip hardening)."""
    allowed = ("manifest.json", "db/", "uploads/")
    manifest: dict | None = None
    n = 0
    with tarfile.open(path, "r:gz") as tar:
        for m in tar:
            n += 1
            if n > MAX_MEMBERS:
                raise ValueError("too many members")
            if m.issym() or m.islnk() or m.isdev():
                raise ValueError(f"unsupported member type: {m.name}")
            name = m.name.lstrip("./")
            if name not in allowed and not name.startswith(("db/", "uploads/")):
                raise ValueError(f"unexpected member in tarball: {m.name}")
            if ".." in m.name.split("/") or m.name.startswith("/"):
                raise ValueError(f"unsafe member path: {m.name}")
            if m.size > MAX_MEMBER_BYTES:
                raise ValueError(f"member too large: {m.name}")
            if name == "manifest.json":
                f = tar.extractfile(m)
                if f is None:
                    raise ValueError("manifest.json is not a regular file")
                manifest = json.loads(f.read().decode("utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("manifest.json is not an object")
    if manifest is None:
        raise ValueError("manifest.json missing")
    if "tables" not in manifest:
        raise ValueError("manifest.json has no tables entry")
    return manifest


def run_import(tar_path: str) -> dict:
    """Execute the import; raises on any unresolvable error (the caller's
    DB transaction/lock discipline makes failures non-destructive)."""
    summary = (
        _import_postgres(tar_path)
        if settings.database_url.startswith("postgres")
        else _import_sqlite(tar_path)
    )

    # uploads: staging inside UPLOAD_DIR (same volume/filesystem), moved
    # into place after the DB transaction has committed
    moved = _import_uploads(tar_path)
    summary["uploads_moved"] = moved
    return summary


# --- PostgreSQL ---------------------------------------------------------------------


def _import_postgres(tar_path: str) -> dict:
    import psycopg2

    from app.services.backup_state import psycopg2_url

    dumped: dict[str, list[str]] = {}
    schema_version = 1
    with tarfile.open(tar_path, "r:gz") as tar:
        m = tar.extractfile("manifest.json")
        if m is not None:
            manifest = json.loads(m.read().decode("utf-8"))
            schema_version = manifest.get("schema_version", 1)
            dumped = manifest.get("table_columns", {}) or {}

        conn = psycopg2.connect(psycopg2_url())
        try:
            with conn.cursor() as cur:
                # one transaction around everything destructive
                cur.execute("BEGIN")
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                live_cols: dict[str, list[str]] = {}
                existing: set[str] = set()
                for t in DUMP_TABLES:
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = %s "
                        "ORDER BY ordinal_position",
                        (t,),
                    )
                    cols: list[str] | None = [r[0] for r in cur.fetchall()]
                    if cols:
                        live_cols[t] = cols
                        existing.add(t)

                # destructive part starts here; any error → ROLLBACK below
                cur.execute(f'TRUNCATE {", ".join(existing)} CASCADE')  # noqa: S608 — fixed names

                loaded: dict[str, int] = {}
                for t in DUMP_TABLES:
                    member = tar.extractfile(f"db/{t}.copy")
                    if member is None:
                        continue  # table absent from this (older) dump
                    if schema_version >= 2 and t in dumped:
                        # columns absent from the live schema (newer dump) are dropped
                        cols = [c for c in dumped[t] if c in live_cols.get(t, [])]
                    elif schema_version == 1 and t not in dumped:
                        # legacy tarball without column lists: only safe when the
                        # column count still matches the live schema
                        first = member.read(1)
                        member.seek(0)
                        if first == b"":
                            loaded[t] = 0
                            continue
                        ncols = member.readline().count(b"\t")
                        member.seek(0)
                        if ncols != len(live_cols.get(t, [])):
                            raise RuntimeError(
                                f"legacy backup (schema_version 1) table '{t}' has {ncols} "
                                f"columns but the live schema has {len(live_cols.get(t, []))} — "
                                "re-export the backup with a compatible version"
                            )
                        cols = None  # full-row COPY
                    else:
                        cols = live_cols.get(t)
                    col_sql = f" ({', '.join(cols)})" if cols else ""
                    cur.copy_expert(f'COPY "{t}"{col_sql} FROM STDIN', member)  # noqa: S608
                    loaded[t] = -1  # filled with real counts below

                # resync serial sequences so future inserts don't collide
                for t in DUMP_TABLES:
                    if t not in loaded or "id" not in live_cols.get(t, []):
                        continue
                    cur.execute(
                        "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                        "COALESCE((SELECT MAX(id) FROM " + t + "), 1), true)",  # noqa: S608
                        (t,),
                    )
                    cur.execute(f'SELECT COUNT(*) FROM "{t}"')  # noqa: S608
                    loaded[t] = int(cur.fetchone()[0])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return {"tables": loaded, "schema_version": schema_version}


# --- SQLite (dev/tests) ---------------------------------------------------------------


def _import_sqlite(tar_path: str) -> dict:
    db_file = settings.database_url.split("///", 1)[-1]
    aux_path: str | None = None
    # uri=True enables URI filenames on this connection — required for
    # ATTACHing the read-only archive copy below
    con = sqlite3.connect(f"file:{db_file}", uri=True, timeout=10)
    try:
        # the manifest decides whether a DB section is expected at all
        with tarfile.open(tar_path, "r:gz") as tar:
            mf = tar.extractfile("manifest.json")
            if mf is not None:
                manifest = json.loads(mf.read().decode("utf-8"))
                schema_version = manifest.get("schema_version", 1)
                dumped_tables = {
                    k
                    for k, v in (manifest.get("tables") or {}).items()
                    if k != "__sqlite_file__"
                }
        have_dumped_rows = bool(dumped_tables)

        with tarfile.open(tar_path, "r:gz") as tar:
            member = None
            for m in tar:
                if m.name.lstrip("./") == "db/clinic.sqlite3":
                    member = m
                    break
            if member is None:
                if have_dumped_rows:
                    raise RuntimeError(
                        "backup lists tables in its manifest but has no "
                        "db/clinic.sqlite3 member"
                    )
                return {"tables": {}, "schema_version": schema_version}  # uploads-only
            fd, aux_path = tempfile.mkstemp(prefix="clinic-import-", suffix=".sqlite3")
            os.close(fd)
            f = tar.extractfile(member)
            assert f is not None
            with open(aux_path, "wb") as out:
                shutil.copyfileobj(f, out)

        con.execute("PRAGMA foreign_keys=OFF")
        # uri=True on the main connection enables URI filenames (read-only aux)
        con.execute(f"ATTACH DATABASE 'file:{aux_path}?mode=ro' AS aux")  # noqa: S608
        try:
            aux_tables = [
                r[0]
                for r in con.execute("SELECT name FROM aux.sqlite_master WHERE type='table'")
                if not r[0].startswith("sqlite_")
            ]
            live_tables = {
                r[0]
                for r in con.execute("SELECT name FROM main.sqlite_master WHERE type='table'")
                if not r[0].startswith("sqlite_")
            }
            live_cols: dict[str, list[str]] = {
                t: [r[1] for r in con.execute(f'PRAGMA main.table_info("{t}")')]  # noqa: S608
                for t in live_tables
            }

            con.execute("BEGIN")
            try:
                # clear every table that exists live or in the dump
                for t in live_tables | set(aux_tables):
                    con.execute(f'DELETE FROM main."{t}"')  # noqa: S608
                loaded: dict[str, int] = {}
                for t in aux_tables:
                    aux_cols = [r[1] for r in con.execute(f'PRAGMA aux.table_info("{t}")')]  # noqa: S608
                    common = [c for c in aux_cols if c in live_cols.get(t, [])]
                    col_sql = ", ".join(f'"{c}"' for c in common)
                    cur = con.execute(
                        f'INSERT INTO main."{t}" ({col_sql}) '
                        f'SELECT {col_sql} FROM aux."{t}"'  # noqa: S608
                    )
                    loaded[t] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        finally:
            con.execute("DETACH DATABASE aux")
    finally:
        if aux_path:
            with contextlib.suppress(OSError):
                os.unlink(aux_path)
        con.close()
    return {"tables": loaded, "schema_version": 0}


# --- uploads -----------------------------------------------------------------------


def _import_uploads(tar_path: str) -> int:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    staging = upload_dir / f".import-{uuid.uuid4().hex[:12]}"
    moved = 0
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            staging.mkdir()
            for m in tar:
                name = m.name.lstrip("./")
                if not name.startswith("uploads/") or m.isdir():
                    continue
                if m.issym() or m.islnk() or m.isdev():
                    continue
                rel = name[len("uploads/") :]
                if not rel or rel.startswith("/") or ".." in rel.split("/"):
                    continue
                dest = staging / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                f = tar.extractfile(m)
                if f is None:
                    continue
                with open(dest, "wb") as out:
                    shutil.copyfileobj(f, out)
        # DB is committed at this point (caller ordering) — move into place
        for src in staging.rglob("*"):
            if src.is_file():
                dest = upload_dir / src.relative_to(staging)
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dest)
                moved += 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return moved
