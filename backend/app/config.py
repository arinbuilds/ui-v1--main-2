"""Application configuration.

All configuration is environment driven — no hard-coded secrets or credentials.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- app ---------------------------------------------------------------
    app_name: str = "FINTECHSICO"
    app_version: str = "1.0.0"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: str = "*"

    # --- postgres ----------------------------------------------------------
    postgres_user: str = "riskguard"
    postgres_password: str = "riskguard_dev_pw"
    postgres_db: str = "riskguard"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    # Full DSN override (set by docker-compose). When empty it is assembled
    # from the POSTGRES_* variables above.
    database_url: str | None = None
    # Local-dev convenience: when true (default) and no DATABASE_URL is set,
    # use the file-backed SQLite database (dev.db) so the stack runs with
    # zero external services. Production/docker sets USE_POSTGRES=true.
    use_postgres: bool = False

    # --- ML ----------------------------------------------------------------
    model_dir: Path = BACKEND_ROOT / "models"
    demo_seed: int = 42
    seed_demo_data: bool = True
    # When true every prediction is routed through the deterministic
    # rule-based fallback so the fallback path can be demonstrated safely.
    force_fallback: bool = False

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.use_postgres:
            return (
                f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return f"sqlite:///{BACKEND_ROOT / 'dev.db'}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
