"""Write a backup tarball (manifest v4) from a database + an uploads dir.

Single implementation of the archive format, shared by two callers:

- the in-app backup job (``app/api/v1/backup.py::_run_backup``) — it always
  encrypts when ``BACKUP_ENCRYPTION_KEY`` is configured and never produces a
  plaintext artifact when it is;
- ``scripts/pack_backup.py`` — a standalone packer for a database that is not
  the running site's own (e.g. a legacy import staged into a scratch DB). It
  writes an UNENCRYPTED ``.tar.gz`` unless a key is passed, because the file
  never leaves the machine the operator packed it on until they choose to
  upload it. The site's importer sniffs the ``PRAXISBK`` magic on upload and
  accepts either kind (see ``services/backup_crypto.py::sniff_and_decrypt``).

Layout (schema_version 4), identical to what the importer expects:
    manifest.json      — schema_version/app_version/table_columns/member_sha256
    db/<table>.copy    — PostgreSQL COPY text (one member per table, FK order),
                         or db/clinic.sqlite3 for a SQLite database
    uploads/<relpath>  — the uploaded patient files (dot-dirs skipped)

Everything streams: tables go through a SpooledTemporaryFile (spills to disk)
and uploads are hashed and added file by file, so a multi-GB volume is never
held in memory. The archive is written to a ``.part`` file and atomically
renamed, so a crash never publishes a half-written artifact.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tarfile
import tempfile
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.tokens import utc_now
from app.services.backup_crypto import encrypt_file, sha256_file
from app.services.backup_state import DUMP_TABLES, psycopg2_url

# Manifest schema this writer produces. The importer refuses anything higher
# (see backup_import.SUPPORTED_SCHEMA_VERSION).
SCHEMA_VERSION = 4

RESTORE_INSTRUCTIONS = (
    "1) create an empty DB and run `alembic upgrade head` "
    "2) for each db/<table>.copy (FK order): "
    'psql -c "COPY <table> (cols...) FROM STDIN" < db/<table>.copy '
    "3) unpack uploads/ into UPLOAD_DIR — or use the in-app import "
    "(POST /admin/backup/import), which is transactional. "
    "An encrypted artifact (PRAXISBK magic, .enc) is decrypted with "
    "BACKUP_ENCRYPTION_KEY during import."
)


def _manifest(app_version: str, app_timezone: str) -> dict[str, Any]:
    return {
        "created_at": utc_now().isoformat(),
        "schema_version": SCHEMA_VERSION,
        "app_version": app_version,
        "app_timezone": app_timezone,
        "tables": {},
        "table_columns": {},
        # sha256 of every member except manifest.json itself (it can't contain
        # its own hash) — the importer verifies them member-by-member BEFORE the
        # destructive transaction, so a corrupted tarball never half-imports
        "member_sha256": {},
        "restore": RESTORE_INSTRUCTIONS,
    }


def _dump_postgres(tar: tarfile.TarFile, manifest: dict, dsn: str, tables: Sequence[str]) -> None:
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            # REPEATABLE READ snapshot so all tables are consistent mid-job
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            for table in tables:
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
                    h = hashlib.sha256()
                    while chunk := buf.read(1024 * 1024):
                        h.update(chunk)
                    manifest["member_sha256"][f"db/{table}.copy"] = h.hexdigest()
                    buf.seek(0)
                    tar.addfile(info, buf)
        conn.rollback()
    finally:
        conn.close()


def _dump_sqlite(tar: tarfile.TarFile, manifest: dict, database_url: str) -> None:
    import sqlite3

    db_file = database_url.split("///", 1)[-1]
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
                r[1] for r in con.execute(f'PRAGMA table_info("{t}")').fetchall()  # noqa: S608
            ]
            manifest["tables"][t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]  # noqa: S608
    finally:
        con.close()
    manifest["member_sha256"]["db/clinic.sqlite3"] = sha256_file(db_file)
    tar.add(db_file, arcname="db/clinic.sqlite3")


def _add_uploads(tar: tarfile.TarFile, manifest: dict, upload_dir: Path) -> int:
    """Stream the uploads volume into the archive. Returns the member count.

    Dot-dirs are runtime staging (e.g. ``.import-*``, ``.backups``) — never
    archived, so a tarball can never contain itself or a half-extracted
    import. Files are named by storage name (``stored_filename``) — never by
    the URL a client might have seen.
    """
    if not upload_dir.is_dir():
        return 0
    member_sha: dict[str, str] = manifest["member_sha256"]
    n_files = 0
    for f in sorted(upload_dir.rglob("*")):
        if f.is_file() and not f.parent.name.startswith("."):
            arcname = f"uploads/{f.relative_to(upload_dir)}"
            member_sha[arcname] = sha256_file(f)
            tar.add(f, arcname=arcname)
            n_files += 1
    return n_files


def build_backup_tarball(
    *,
    database_url: str,
    upload_dir: str | Path,
    out_path: str | Path,
    app_version: str,
    encryption_key: str = "",
    app_timezone: str = "",
    skip_tables: Sequence[str] = (),
) -> dict[str, Any]:
    """Write one complete tarball at ``out_path`` and return its metadata.

    ``out_path`` is published atomically: the archive is built as
    ``<name>.<random>.part`` next to it and ``os.replace``d into place, so a
    reader never sees a partial artifact and an existing file at ``out_path``
    is only replaced once the new one is complete.

    ``skip_tables`` drops tables from the dump entirely — they are neither
    copied nor listed in the manifest, so the importer leaves them alone
    (its TRUNCATE covers only the tables the tarball actually carries). The
    packer script uses it to keep accounts out of a legacy-import tarball.

    Returns ``{"path", "size_bytes", "sha256", "encrypted", "tables",
    "uploads_files", "app_version", "schema_version", "manifest"}``; ``sha256``
    is of the FINAL artifact (ciphertext when encrypted) — the value a client
    can pass as ``expected_sha256`` on import. ``manifest`` is the dict that
    was written, so a caller can report on the contents without re-opening
    the archive (an encrypted artifact is not readable as a tarball).
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tables = [t for t in DUMP_TABLES if t not in set(skip_tables)]

    manifest = _manifest(app_version, app_timezone or settings.app_timezone)
    fd, part = tempfile.mkstemp(prefix=f"{out.stem}-", suffix=".part", dir=out.parent)
    os.close(fd)
    path = part
    try:
        with tarfile.open(path, "w:gz") as tar:
            if database_url.startswith("postgres"):
                _dump_postgres(tar, manifest, psycopg2_url(database_url), tables)
            else:
                _dump_sqlite(tar, manifest, database_url)

            manifest["uploads_files"] = _add_uploads(tar, manifest, Path(upload_dir))

            m = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(m)
            tar.addfile(info, BytesIO(m))

        # encryption wraps the finished tarball; the plaintext is removed so
        # only the encrypted artifact is ever published
        encrypted = False
        if encryption_key:
            enc_path = path + ".enc"
            encrypt_file(path, enc_path, encryption_key)
            os.unlink(path)
            path = enc_path
            encrypted = True

        digest = sha256_file(path)
        os.replace(path, out)
        path = ""
        return {
            "path": str(out),
            "size_bytes": os.path.getsize(out),
            "sha256": digest,
            "encrypted": encrypted,
            "tables": len(manifest["tables"]),
            "uploads_files": manifest["uploads_files"],
            "app_version": app_version,
            "schema_version": SCHEMA_VERSION,
            "manifest": manifest,
        }
    finally:
        if path and os.path.exists(path):
            with contextlib.suppress(OSError):
                os.unlink(path)
