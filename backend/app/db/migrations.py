"""Database migration at application startup (fail-fast).

`run_migrations()` is called from the FastAPI lifespan BEFORE anything else
touches the database, so every launch path (container, bare-metal uvicorn,
scripts) serves a fully-migrated schema or refuses to boot — uvicorn exits
nonzero when the lifespan raises, and the container restart-loops.

Alembic runs with a sync engine; the URL dialect is stripped the same way
alembic/env.py does it (psycopg2/sqlite3 are hard dependencies already).
The alembic Config is built programmatically with an absolute script_location
(derived from the app package path) so the caller's CWD is irrelevant.

Dev/CI databases built by `Base.metadata.create_all` carry no
`alembic_version` table; running the (partially SQLite-incompatible)
migrations over them would collide with existing tables. Such databases are
stamped at head instead — their schema is current by construction. A fresh
EMPTY SQLite database is create_all-built + stamped (SQLite cannot run the
full chain); fresh PostgreSQL always runs the real migrations.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import settings

logger = logging.getLogger("clinic.migrations")
def sync_url() -> str:
    """Strip async dialect drivers — alembic and scripts run sync engines."""
    url = settings.database_url
    for async_prefix, sync_prefix in (
        ("sqlite+aiosqlite", "sqlite"),
        ("postgresql+asyncpg", "postgresql+psycopg2"),
    ):
        if url.startswith(async_prefix):
            return url.replace(async_prefix, sync_prefix, 1)
    return url


def _script_location() -> str:
    # app/db/migrations.py -> backend/alembic (in-container: /srv/alembic)
    return str(Path(__file__).resolve().parents[2] / "alembic")


def _alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", _script_location())
    return cfg


def run_migrations() -> None:
    """Bring the database to the head revision; raise on any failure."""
    cfg = _alembic_config()
    engine = create_engine(sync_url())
    try:
        is_sqlite = engine.dialect.name == "sqlite"
        insp = inspect(engine)
        has_version = insp.has_table("alembic_version")
        has_domain = insp.has_table("users")
        if not has_version:
            if is_sqlite:
                # SQLite cannot run the whole chain (constraint-style
                # migrations ALTER constraints, not supported there) and is
                # dev/test-only: build the schema from the models, like the
                # test suite does, then stamp. PostgreSQL always migrates.
                from app.models import Base

                if not has_domain:
                    logger.info("Empty SQLite database — create_all + stamp head (dev).")
                    Base.metadata.create_all(engine)
                logger.info("Stamping SQLite database at head.")
                command.stamp(cfg, "head")
                return
            if has_domain:
                logger.info(
                    "No alembic_version but domain tables exist "
                    "(create_all-built database) — stamping head."
                )
                command.stamp(cfg, "head")
                return
            logger.info("Empty database — running all migrations.")
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
