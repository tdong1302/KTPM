from pathlib import Path

from scripts.preflight import database_identity, is_disposable_test_database, parse_dotenv


def test_database_identity_never_contains_credentials() -> None:
    identity = database_identity(
        "postgresql+psycopg://private-user:private-password@localhost:5433/eventhub_test"
    )

    assert identity == ("localhost", 5433, "eventhub_test")
    assert "private" not in repr(identity)


def test_disposable_database_requires_an_unmistakable_name() -> None:
    safe, reason = is_disposable_test_database(
        "postgresql+psycopg://user:password@localhost:5433/eventhub"
    )

    assert not safe
    assert "database name" in reason


def test_disposable_database_must_differ_from_development_database() -> None:
    url = "postgresql+psycopg://user:password@localhost:5433/eventhub_test"

    safe, reason = is_disposable_test_database(url, url)

    assert not safe
    assert "must not be the same" in reason


def test_disposable_database_rejects_protected_environment_names() -> None:
    safe, reason = is_disposable_test_database(
        "postgresql+psycopg://user:password@localhost:5433/eventhub_production_test"
    )

    assert not safe
    assert "protected environment" in reason


def test_disposable_database_accepts_ci_database_without_exposing_password() -> None:
    safe, detail = is_disposable_test_database(
        "postgresql+psycopg://ci-user:super-secret@postgres:5432/eventhub_ci"
    )

    assert safe
    assert detail == "isolated PostgreSQL target postgres:5432, database=eventhub_ci"
    assert "super-secret" not in detail


def test_parse_dotenv_returns_names_and_values_without_interpreting_comments(
    tmp_path: Path,
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("# ignored\nDATABASE_URL='postgresql://local/db'\nEMPTY=\n", encoding="utf-8")

    assert parse_dotenv(dotenv) == {
        "DATABASE_URL": "postgresql://local/db",
        "EMPTY": "",
    }
