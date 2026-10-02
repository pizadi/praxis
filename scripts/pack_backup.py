#!/usr/bin/env python3
"""Package a database + an uploads directory into a website-ingestible backup.

Writes a manifest-v4 tarball (``db/<table>.copy`` in PostgreSQL COPY text
format, ``uploads/<name>``, ``manifest.json`` with a sha256 for every member)
that ``POST /admin/backup/import`` ingests transactionally — the same format
the site's own backup button produces, via the same writer
(``app/services/backup_dump.py``).

This is the second half of the legacy-import pipeline::

    migrate_sqlite.py  --source old.db --files patient_files \\
                       --database-url <scratch PG> --upload-dir work/legacy --apply
    pack_backup.py     --database-url <scratch PG> --upload-dir work/legacy \\
                       --out work/legacy-import.tar.gz
    # then upload work/legacy-import.tar.gz in the site's backup page

Encryption: UNENCRYPTED by default — the artifact is a plain ``.tar.gz`` that
stays on the machine you packed it on until you choose to upload it. Pass
``--encryption-key`` (or set ``BACKUP_ENCRYPTION_KEY``) and it is wrapped in
AES-256-GCM (``PRAXISBK`` magic, ``.enc``) instead. The site detects which it
is from the magic bytes on upload, not from the file name, so both import.

Accounts are EXCLUDED by default: the importer truncates every table a tarball
carries, so a pack of a database that never ran ``bootstrap_admin()`` would
delete the site's admin and lock everyone out. ``--include-auth`` opts back in
for a true full mirror (and note that ``roles`` and ``users`` must always be
taken together — truncating roles cascades to users).

Usage:
  python pack_backup.py --database-url postgresql+asyncpg://u:p@host:5432/db \\
      --upload-dir work/legacy-uploads --out work/legacy-import.tar.gz \\
      [--encryption-key KEY] [--include-auth] [--app-version X] [--force]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import __version__
from app.services.backup_dump import build_backup_tarball
from app.services.backup_state import (
    AUTH_TABLES,
    DUMP_TABLES,
    psycopg2_url,
)

log = logging.getLogger("pack")


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def preflight(database_url: str, tables: list[str]) -> dict[str, int]:
    """Fail loudly BEFORE packing: the tarball is only ingestible if the
    source database is migrated to head and the tables we dump actually exist.

    Returns {table: row count} for the tables that are present.
    """
    if not database_url.startswith("postgres"):
        raise SystemExit(
            "--database-url must be a PostgreSQL DSN: the site's importer reads "
            "db/<table>.copy members (PostgreSQL COPY text) and silently ignores "
            "a db/clinic.sqlite3 member when it runs on PostgreSQL."
        )
    import psycopg2

    conn = psycopg2.connect(psycopg2_url(database_url))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.alembic_version')")
            if cur.fetchone()[0] is None:
                raise SystemExit(
                    "the target database has no alembic_version — run "
                    "`alembic upgrade head` against it before packing"
                )
            cur.execute("SELECT version_num FROM alembic_version")
            version = cur.fetchone()[0]
            counts: dict[str, int] = {}
            for t in tables:
                cur.execute("SELECT to_regclass(%s)", (f"public.{t}",))
                if cur.fetchone()[0] is None:
                    continue
                cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                counts[t] = cur.fetchone()[0]
    finally:
        conn.close()
    log.info("source database at alembic revision %s", version)
    return counts


def print_manifest(manifest: dict) -> None:
    """Echo what the tarball carries, so the operator can eyeball the import
    before wiping anything. Takes the manifest the writer returned — an
    encrypted artifact cannot be re-read as a tarball to recover it."""
    tables = manifest.get("tables", {})
    log.info("tarball contents (schema_version %s, app_version %s):",
             manifest.get("schema_version"), manifest.get("app_version"))
    for name, count in tables.items():
        log.info("  %-28s %s", name, count)
    log.info("  %-28s %s", "uploads/*", manifest.get("uploads_files", 0))
    skipped = sorted(AUTH_TABLES - set(tables))
    if skipped:
        log.info("  NOT in the tarball (--include-auth to add): %s", ", ".join(skipped))
    total = sum(v for k, v in tables.items() if k != "__sqlite_file__")
    log.info("  %d tables, %d rows", len([k for k in tables if k != "__sqlite_file__"]), total)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--database-url", required=True, help="PostgreSQL DSN of the database to pack"
    )
    parser.add_argument(
        "--upload-dir", required=True, type=Path, help="Directory whose files become uploads/*"
    )
    parser.add_argument("--out", required=True, type=Path, help="Output tarball path")
    key_help = "AES-256-GCM key; omit (and leave BACKUP_ENCRYPTION_KEY unset) for a plain tar.gz"
    parser.add_argument("--encryption-key", default="", help=key_help)
    parser.add_argument(
        "--include-auth",
        action="store_true",
        help="Also dump roles/users/sessions (replaces the site's accounts on import)",
    )
    parser.add_argument(
        "--app-version", default=__version__,
        help=f"app_version recorded in the manifest (default: {__version__})",
    )
    parser.add_argument(
        "--app-timezone", default="", help="app_timezone recorded in the manifest"
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing --out file")
    args = parser.parse_args()

    if not args.upload_dir.is_dir():
        log.error("--upload-dir %s is not a directory", args.upload_dir)
        return 2
    if args.out.exists() and not args.force:
        log.error("%s already exists — pass --force to overwrite", args.out)
        return 2

    # BACKUP_ENCRYPTION_KEY is honoured so the script and the site can be
    # configured the same way; an explicit --encryption-key always wins.
    key = args.encryption_key or os.environ.get("BACKUP_ENCRYPTION_KEY", "")
    skip = () if args.include_auth else sorted(AUTH_TABLES)
    out = args.out
    if key and not out.name.endswith(".enc"):
        out = out.with_name(out.name + ".enc")

    tables = [t for t in DUMP_TABLES if t not in set(skip)]
    counts = preflight(args.database_url, tables)
    missing = [t for t in tables if t not in counts]
    if missing:
        log.error("tables missing from the source database: %s", ", ".join(missing))
        return 3
    log.info(
        "packing %d tables (%s rows) + %d upload(s) from %s",
        len(counts), sum(counts.values()), sum(1 for _ in args.upload_dir.rglob("*") if _.is_file()),
        args.upload_dir,
    )
    if not args.include_auth:
        log.info("excluding accounts: %s (--include-auth to include them)", ", ".join(skip))

    result = build_backup_tarball(
        database_url=args.database_url,
        upload_dir=args.upload_dir,
        out_path=out,
        encryption_key=key,
        app_version=args.app_version,
        app_timezone=args.app_timezone,
        skip_tables=skip,
    )

    print_manifest(result["manifest"])
    log.info("")
    log.info("artifact : %s", result["path"])
    log.info("size     : %s", human(int(result["size_bytes"])))
    log.info("encrypted: %s", "yes (AES-256-GCM)" if result["encrypted"] else "no (plain .tar.gz)")
    log.info("sha256   : %s", result["sha256"])
    log.info("")
    log.info("Upload it from the site's backup page, or POST it to")
    log.info("POST /api/v1/admin/backup/import as multipart form data. Pass the sha256")
    log.info("above as expected_sha256 to have the server verify it before importing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
