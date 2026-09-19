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
    "questionnaire_templates",
    "users",
    "patients",
    "appointments",
    "questionnaire_responses",
    "transactions",
    "attachments",
    "patient_tags",
    "patient_diagnoses",
    "audit_log",
    "login_audit",
    "refresh_tokens",
)

JOB_LOCK = threading.Lock()


def psycopg2_url() -> str:
    """asyncpg DSN → plain psycopg2 DSN (psycopg2 can't parse dialect schemes)."""
    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return url
