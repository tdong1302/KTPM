"""Configuration validation and safe deployment defaults."""

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def isolate_settings_from_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep configuration tests deterministic under developer and CI environments."""
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)


def test_local_environment_allows_documented_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert settings.db_pool_size == 5


def test_production_rejects_the_development_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(environment="production", jwt_secret="unsafe", _env_file=None)


def test_production_accepts_a_private_jwt_secret() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="a-private-production-secret-that-is-long-enough",
        _env_file=None,
    )

    assert settings.environment == "production"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("db_pool_size", 0),
        ("db_max_overflow", -1),
        ("db_pool_timeout", 0),
        ("jwt_expires_minutes", 0),
        ("bcrypt_rounds", 3),
        ("bcrypt_rounds", 32),
    ],
)
def test_invalid_operational_limits_are_rejected(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
