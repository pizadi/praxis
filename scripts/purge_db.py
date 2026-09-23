#!/usr/bin/env python3
"""Completely purge the clinic database — every table, INCLUDING users —
then rebuild it from scratch: migrations to head + a fresh admin account.

Usage:
  python purge_db.py                                  # dry run: prints the plan
  python purge_db.py --yes                            # purge the default DSN
  python purge_db.py --database-url URL --yes         # purge an explicit DSN
  python purge_db.py --yes --uploads                  # also empty UPLOAD_DIR
  python purge_db.py --yes --no-snapshot              # skip the safety snapshot

IMPORTANT: stop the app container first (`docker compose stop api`) — a
running api keeps transactions open on the target DB, which (a) can block
the DROP SCHEMA on locks and (b) races the rebuild (in-flight writes are
lost). The DROP carries a lock timeout and refuses loudly instead of
hanging when it detects exactly that situation.

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

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

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
    "--disconnect-others",
    action="store_true",
    help="Terminate all other sessions on the target DB right before the drop — "
    "clears leftover lock holders (idle DB-tool sessions block DROP SCHEMA). "
    "Safe: the purge replaces the whole database anyway.",
)
parser.add_argument(
    "--container",
    default="new-patients-db-1",
    help="docker container hosting PostgreSQL (for the snapshot)",
)


def _urls():
    """(database_url, sync_url) — app imports must happen AFTER main() has
    landed the --database-url override in the environment (pydantic-settings
    caches at first import)."""
    from app.core.config import settings
    from app.db.migrations import sync_url

    return settings.database_url, sync_url()


def _lock_wait_failure(exc: SQLAlchemyError) -> str | None:
    """A lock/statement timeout while dropping the schema — map it to the
    user-facing hint (None = some other error, re-raise as-is)."""
    pgcode = getattr(getattr(exc, "orig", None), "pgcode", None) or ""
    if pgcode in ("55P03", "57014"):  # lock_not_available / query_canceled
        return (
            "DROP SCHEMA timed out waiting for locks — something is connected to "
            "the target database and holding/hopping locks (the running api "
            "container, typically). Stop it first: docker compose stop api — "
            "then re-run this purge."
        )
    return None


def _engine() -> Engine:
    """One-shot CLI — no pooling: every close() is a real close (the backend
    exits at once). A pooled connection abandoned to the garbage collector
    lingers as an 'idle in transaction' session that our own
    --disconnect-others sweep then kills, and the pool's deferred reset
    logs a scary 'server closed the connection unexpectedly' afterwards."""
    _, sync = _urls()
    return create_engine(sync, poolclass=NullPool)


def current_revision() -> str:
    engine = _engine()
    try:
        if not inspect(engine).has_table("alembic_version"):
            return "none (no alembic_version)"
        with engine.connect() as conn:  # explicit scope — never GC-finalized
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return str(rev) if rev else "none (empty alembic_version)"
    except (SQLAlchemyError, OSError) as exc:  # unreachable DB — a purge would fail anyway
        sys.exit(f"Cannot reach the target database: {exc}")
    finally:
        engine.dispose()


def is_sqlite() -> bool:
    _, sync = _urls()
    return sync.startswith("sqlite")


def report_other_backends() -> None:
    """Warn loudly when something else is connected to the target database —
    a purge must run while the app is stopped (lock hangs + write races)."""
    if is_sqlite():
        return
    engine = _engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT pid, state, application_name FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                )
            ).fetchall()
    except SQLAlchemyError:
        return
    finally:
        engine.dispose()
    if rows:
        print(f"WARNING: {len(rows)} other connection(s) to the target database:")
        for pid, state, app_name in rows:
            print(f"  pid {pid} ({state}, {app_name or 'application unknown'})")
        print("Stop the app container first: docker compose stop api")


def take_snapshot(container: str) -> None:
    import snapshot_db

    if is_sqlite():
        _, sync = _urls()
        db_path = Path(sync.replace("sqlite://", "", 1))
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        out = snapshot_db.target_path("pre-purge", ".db")
        snapshot_db.snapshot_sqlite(db_path, out)
        print(f"snapshot: {out} ({out.stat().st_size} bytes)")
    else:
        out = snapshot_db.target_path("pre-purge", ".dump")
        snapshot_db.snapshot_postgres(container, out)
        snapshot_db.validate_postgres(container, out)
        print(f"snapshot: {out} ({out.stat().st_size} bytes) — validated")


def disconnect_others() -> None:
    """pg_terminate_backend every other session on the target database.

    The purge replaces the whole database, so no other session can survive
    it meaningfully — this just clears lock holders (a DB tool left idle in
    transaction, a stray local session) that would block the DROP even with
    the app container stopped.
    """
    if is_sqlite():
        return
    engine = _engine()
    try:
        with engine.connect() as conn:
            n = 0
            for (killed,) in conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                )
            ):
                n += 1 if killed else 0
    finally:
        engine.dispose()
    if n:
        print(f"disconnected {n} other session(s) on the target database")


def drop_schema() -> None:
    engine = _engine()
    try:
        with engine.connect() as conn:
            if is_sqlite():
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                names = inspect(engine).get_table_names()
                for name in names:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
                conn.execute(text("PRAGMA foreign_keys = ON"))
            else:
                # DDL waits on conflicting locks FOREVER by default (no
                # lock_timeout in PostgreSQL) — cap the wait so a running
                # app fails the purge loudly instead of hanging it.
                conn.execute(text("SET lock_timeout = '10s'"))
                conn.execute(text("SET statement_timeout = '60s'"))
                conn.execute(text("DROP SCHEMA public CASCADE"))
                conn.execute(text("CREATE SCHEMA public"))
            conn.commit()
    except SQLAlchemyError as exc:
        hint = _lock_wait_failure(exc)
        if hint:
            sys.exit(hint)
        raise
    finally:
        engine.dispose()


def purge_uploads() -> None:
    from app.core.config import settings

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
    args = parser.parse_args()
    if args.database_url:
        # The async engine binds settings.database_url at import time — the
        # override must land in the environment BEFORE any app.* import.
        os.environ["DATABASE_URL"] = args.database_url

    from app.core.config import settings
    from app.db.migrations import run_migrations

    target = settings.database_url
    print(f"target database : {target}")
    print(f"current revision: {current_revision()}")
    print(f"uploads dir     : {settings.upload_dir}{'' if args.uploads else ' (kept)'}")
    print(f"admin to recreate: {settings.bootstrap_admin_username}")
    report_other_backends()

    if not args.yes:
        print("\nDRY RUN — nothing was changed. Re-run with --yes to purge.")
        return 0

    if not args.no_snapshot:
        print("taking snapshot first…")
        take_snapshot(args.container)

    print("dropping schema…")
    if args.disconnect_others:
        disconnect_others()
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
