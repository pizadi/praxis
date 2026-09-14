import os
from functools import lru_cache

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

    # --- CORS ---
    cors_origins: str = "http://localhost:5173"

    # --- Uploads ---
    upload_dir: str = "data/uploads"
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB

    # --- App ---
    app_timezone: str = "Asia/Tehran"
    api_v1_prefix: str = "/api/v1"

    # --- Bootstrap admin (created only if users table is empty) ---
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


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
