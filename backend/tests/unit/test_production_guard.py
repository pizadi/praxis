"""Production boot guard: CLINIC_ENV=production must never boot on SQLite —
a lost DATABASE_URL env var would otherwise silently "work" while writing
real patient data into a throwaway file."""

import pytest

from app.core.config import settings, validate_production_secrets

PROD_SECRET = "x" * 48  # long enough to pass the dev-key check


def _allow_pg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", PROD_SECRET)
    monkeypatch.setattr(settings, "bootstrap_admin_password", "real-one-42")


def test_production_refuses_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLINIC_ENV", "production")
    _allow_pg(monkeypatch)
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///data/clinic.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        validate_production_secrets()


def test_production_accepts_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLINIC_ENV", "production")
    _allow_pg(monkeypatch)
    monkeypatch.setattr(
        settings, "database_url", "postgresql+asyncpg://u:p@db:5432/clinic"
    )
    validate_production_secrets()  # no raise


def test_non_production_keeps_sqlite_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLINIC_ENV", raising=False)
    validate_production_secrets()  # dev SQLite default — no raise
