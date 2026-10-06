"""Application configuration, read from environment / .env."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production-this-is-a-local-only-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "EventHub-KTPM"
    environment: str = "local"

    database_url: str = "postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_ktpm"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout: int = Field(default=30, gt=0)
    db_echo: bool = False
    # Create tables at startup instead of running Alembic. Convenient for CI and for
    # the Kaggle benchmark notebook where running a migration tool is extra friction.
    db_auto_create: bool = False

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = Field(default=1440, gt=0)

    bcrypt_rounds: int = Field(default=12, ge=4, le=31)

    event_completion_poll_seconds: float = Field(default=60, gt=0, le=3600)
    event_completion_batch_size: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def reject_insecure_production_secret(self) -> "Settings":
        if self.environment.strip().lower() in {"prod", "production"}:
            if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be replaced with at least 32 characters in production"
                )
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
