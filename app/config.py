from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All values can be overridden with ORDERHUB_* env vars."""

    model_config = SettingsConfigDict(
        env_prefix="ORDERHUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Order Hub"
    environment: str = "production"
    database_url: str = "sqlite:///./orderhub.db"
    redis_url: str | None = None
    jwt_secret: str = "change-me-32-bytes-minimum-please"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_minutes: int = 60 * 24 * 7
    pbkdf2_iterations: int = 260_000
    admin_username: str = "admin"
    admin_password: str = "change-me-admin"
    analyst_username: str = "analyst"
    analyst_password: str = "change-me-analyst"
    viewer_username: str = "viewer"
    viewer_password: str = "change-me-viewer"
    seed_default_users: bool = False
    source_dir: Path = Path("data/reference")
    auto_create_tables: bool = False
    cache_ttl_seconds: int = 60
    log_level: str = "INFO"
    cors_origins: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
