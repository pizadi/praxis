"""Shared backup/import job primitives.

One job (backup OR import) may run at a time — both hold JOB_LOCK for their
whole duration. Also home to the dump table order and the psycopg2 DSN
helper, so the API router and the import service share one source of truth.
"""

import threading

from app.core.config import settings

# domain tables in FK-safe dump order
DUMP_TABLES = (
    "roles",
    "tags",
    "diagnoses",
    "prescription_items",
    "questionnaire_templates",
    "users",
    "patients",
    "appointments",
    "questionnaire_responses",
    "transactions",
    "attachments",
    "prescriptions",
    "prescription_item_links",
    "patient_tags",
    "patient_diagnoses",
    "audit_log",
    "login_audit",
    "refresh_tokens",
)

# Accounts + session state. Dumping these REPLACES them on import (the
# importer truncates every table the tarball carries), so a tarball built from
# a database that never ran bootstrap_admin() would wipe the site's admin and
# lock everyone out. Standalone packers exclude them by default
# (scripts/pack_backup.py --include-auth opts back in); the site's own backup
# always includes them — it is a backup of itself.
AUTH_TABLES = frozenset({"roles", "users", "login_audit", "refresh_tokens"})

JOB_LOCK = threading.Lock()


def psycopg2_url(url: str | None = None) -> str:
    """asyncpg DSN → plain psycopg2 DSN (psycopg2 can't parse dialect schemes).

    Defaults to the configured DSN; ``scripts/pack_backup.py`` passes the
    database it was pointed at instead of the running site's.
    """
    url = url or settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return url
