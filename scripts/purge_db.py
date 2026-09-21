#!/usr/bin/env python3
"""Completely purge the clinic database — every table, INCLUDING users —
then rebuild it from scratch: migrations to head + a fresh admin account.

Usage:
  python purge_db.py                                  # dry run: prints the plan
  python purge_db.py --yes                            # purge the default DSN
  python purge_db.py --database-url URL --yes         # purge an explicit DSN
  python purge_db.py --yes --uploads                  # also empty UPLOAD_DIR
  python purge_db.py --yes --no-snapshot              # skip the safety snapshot

The default DSN comes from DATABASE_URL / the .env file — printed LOUDLY
before anything happens; nothing is touched without --yes.

Safety net: unless --no-snapshot is passed, a snapshot is taken FIRST
(scripts/snapshot_db.py — pg_dump via docker exec for PostgreSQL, file copy
for SQLite). A failed snapshot aborts the purge.

The admin account is recreated by the app's bootstrap (BOOTSTRAP_ADMIN_* /
app.core.config settings) — only the username is ever printed, never the
password. Uploaded files are left alone unless --uploads (they would be
orphaned; the automatic uploads purge sweeps them within its 24h grace).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--database-url",
    help="DSN to purge (same format as DATABASE_URL, async drivers). Default: settings/env.",
)
parser.add_argument("--yes", action="store_true", help="Actually purge (default: dry run)")
parser.add_argument("--uploads", action="store_true", help="Also empty the uploads directory")
parser.add_argument(
    "--no-snapshot", action="store_true", help="Skip the pre-purge snapshot (dangerous)"
)
parser.add_argument(
    "--container",
    default="new-patients-db-1",
    help="docker container hosting PostgreSQL (for the snapshot)",
)
args = parser.parse_args()

if args.database_url:
    # The async engine binds settings.database_url at import time — the
    # override must land in the environment BEFORE any app.* import.
    os.environ["DATABASE_URL"] = args.database_url

from app.core.config import settings  # noqa: E402
from app.db.migrations import run_migrations, sync_url  # noqa: E402


def current_revision() -> str:
    engine = create_engine(sync_url())
    try:
        if not inspect(engine).has_table("alembic_version"):
            return "none (no alembic_version)"
        rev = engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar()
        return str(rev) if rev else "none (empty alembic_version)"
    except Exception as exc:  # unreachable DB etc. — a purge would fail anyway
        sys.exit(f"Cannot reach the target database: {exc}")
    finally:
        engine.dispose()


def is_sqlite() -> bool:
    return sync_url().startswith("sqlite")


def take_snapshot() -> None:
    if is_sqlite():
        import snapshot_db

        db_path = Path(sync_url().replace("sqlite://", "", 1))
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        out = snapshot_db.target_path("pre-purge", ".db")
        snapshot_db.snapshot_sqlite(db_path, out)
        print(f"snapshot: {out} ({out.stat().st_size} bytes)")
    else:
        import snapshot_db

        out = snapshot_db.target_path("pre-purge", ".dump")
        snapshot_db.snapshot_postgres(args.container, out)
        snapshot_db.validate_postgres(args.container, out)
        print(f"snapshot: {out} ({out.stat().st_size} bytes) — validated")


def drop_schema() -> None:
    engine = create_engine(sync_url())
    try:
        with engine.connect() as conn:
            if is_sqlite():
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                names = inspect(engine).get_table_names()
                for name in names:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))  # noqa: S608
                conn.execute(text("PRAGMA foreign_keys = ON"))
            else:
                conn.execute(text("DROP SCHEMA public CASCADE"))
                conn.execute(text("CREATE SCHEMA public"))
            conn.commit()
    finally:
        engine.dispose()


def purge_uploads() -> None:
    upload_dir = Path(settings.upload_dir)
    if not upload_dir.is_absolute():
        upload_dir = Path.cwd() / upload_dir
    count = 0
    if upload_dir.is_dir():
        for entry in upload_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            count += 1
    print(f"uploads: emptied {upload_dir} ({count} entries)")


def main() -> int:
    target = settings.database_url
    print(f"target database : {target}")
    print(f"current revision: {current_revision()}")
    print(f"uploads dir     : {settings.upload_dir}{'' if args.uploads else ' (kept)'}")
    print(f"admin to recreate: {settings.bootstrap_admin_username}")

    if not args.yes:
        print("\nDRY RUN — nothing was changed. Re-run with --yes to purge.")
        return 0

    if not args.no_snapshot:
        print("taking snapshot first…")
        take_snapshot()

    print("dropping schema…")
    drop_schema()

    print("migrating to head…")
    run_migrations()

    print("bootstrapping admin…")
    from app.main import bootstrap_admin

    asyncio.run(bootstrap_admin())

    if args.uploads:
        purge_uploads()

    print(f"done — revision {current_revision()}, admin '{settings.bootstrap_admin_username}' recreated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
