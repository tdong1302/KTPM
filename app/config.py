"""Application configuration, read from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "EventHub-KTPM"
    environment: str = "local"

    database_url: str = "postgresql+psycopg://eventhub:eventhub@localhost:5432/eventhub_ktpm"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_echo: bool = False
    # Create tables at startup instead of running Alembic. Convenient for CI and for
    # the Kaggle benchmark notebook where running a migration tool is extra friction.
    db_auto_create: bool = False

    jwt_secret: str = "change-me-in-production-this-is-a-local-only-secret"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 1440

    bcrypt_rounds: int = 12

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
