import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///data/clinic.db"

    # --- Auth ---
    secret_key: str = "dev-insecure-secret-key-change-in-prod"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"

    # --- Login throttle (per-username, window-based) ---
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    # --- CORS ---
    cors_origins: str = "http://localhost:5173"

    # --- Uploads ---
    upload_dir: str = "data/uploads"
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB

    # --- App ---
    app_timezone: str = "Asia/Tehran"
    api_v1_prefix: str = "/api/v1"

    # --- Backup tarballs ---
    # Where backup artifacts live. Empty = <upload_dir>/.backups — a hidden
    # dir on the persistent uploads volume: it survives container recreation,
    # the uploads purge never descends into hidden dirs, and the archive
    # itself skips dot-dirs (the tarball can never include itself).
    backup_dir: str = ""
    # AES-256-GCM passphrase for downloaded artifacts (empty = no encryption).
    # The key unlocks IMPORTS of encrypted tarballs too — losing it means
    # losing the backups, so store it in a password manager.
    backup_encryption_key: str = ""
    # Stale-backup warning: when the last successful backup is older than
    # this many days, admins see a banner (0 disables the warning).
    backup_stale_days: int = 7

    # --- Bootstrap admin (created only if users table is empty) ---
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def backup_dir_resolved(self) -> Path:
        return Path(self.backup_dir) if self.backup_dir else Path(self.upload_dir) / ".backups"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def validate_production_secrets() -> None:
    """Abort startup with insecure defaults in production."""
    if os.environ.get("CLINIC_ENV") == "production":
        if settings.secret_key.startswith("dev-insecure"):
            raise RuntimeError("Refusing to run in production with the dev SECRET_KEY.")
        if settings.bootstrap_admin_password in {"admin123", "change-me-too", ""}:
            raise RuntimeError("Refusing to run in production with a default admin password.")


validate_production_secrets()
