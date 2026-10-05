"""Safe host readiness checks for local development and PostgreSQL verification."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    "docker-compose.yml",
    "Dockerfile",
    "alembic.ini",
)
ENV_KEYS = {
    "APP_NAME",
    "ENVIRONMENT",
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT",
    "DB_ECHO",
    "DB_AUTO_CREATE",
    "JWT_SECRET",
    "JWT_ALGORITHM",
    "JWT_EXPIRES_MINUTES",
    "BCRYPT_ROUNDS",
}
DISPOSABLE_MARKERS = ("test", "disposable", "ci", "tmp", "temporary")
PROTECTED_MARKERS = ("prod", "production", "stage", "staging", "dev", "development")


@dataclass(frozen=True)
class Result:
    level: str
    check: str
    detail: str


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def database_identity(url: str) -> tuple[str, int, str] | None:
    try:
        parsed = urlsplit(url)
        if not parsed.scheme.startswith("postgresql") or not parsed.hostname:
            return None
        return parsed.hostname.lower(), parsed.port or 5432, unquote(parsed.path.lstrip("/"))
    except ValueError:
        return None


def is_disposable_test_database(test_url: str, development_url: str = "") -> tuple[bool, str]:
    identity = database_identity(test_url)
    if identity is None:
        return False, "TEST_DATABASE_URL must be a PostgreSQL URL with a host and database name"
    host, port, database = identity
    name_tokens = set(filter(None, re.split(r"[^a-z0-9]+", database.lower())))
    if name_tokens.intersection(PROTECTED_MARKERS):
        return False, "test database name contains a protected environment marker"
    if not name_tokens.intersection(DISPOSABLE_MARKERS):
        return False, "test database name must contain test, disposable, ci, tmp, or temporary"
    development_identity = database_identity(development_url) if development_url else None
    if development_identity == identity:
        return False, "test database must not be the same endpoint/database as DATABASE_URL"
    return True, f"isolated PostgreSQL target {host}:{port}, database={database}"


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def command_ok(command: list[str]) -> bool:
    try:
        return (
            subprocess.run(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            return None
        return (completed.stdout or completed.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def add(results: list[Result], level: str, check: str, detail: str) -> None:
    results.append(Result(level, check, detail))


def check_environment(mode: str) -> list[Result]:
    results: list[Result] = []
    blocking_infra = mode != "api-only"

    add(results, "PASS", "Host", platform.platform())

    if sys.version_info >= (3, 11):
        add(results, "PASS", "Python", f"{sys.version.split()[0]} is supported")
    else:
        add(results, "FAIL", "Python", "Python 3.11 or newer is required")

    uv = shutil.which("uv")
    uv_version = command_version([uv, "--version"]) if uv else None
    add(
        results,
        "PASS" if uv_version else "FAIL",
        "uv",
        uv_version or "not found on PATH",
    )

    missing_files = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    add(
        results,
        "FAIL" if missing_files else "PASS",
        "Repository files",
        "missing: " + ", ".join(missing_files) if missing_files else "all required files exist",
    )

    example_values = parse_dotenv(ROOT / ".env.example")
    missing_example_keys = sorted(ENV_KEYS - set(example_values))
    add(
        results,
        "FAIL" if missing_example_keys else "PASS",
        ".env.example",
        "missing keys: " + ", ".join(missing_example_keys)
        if missing_example_keys
        else "contains all application setting names",
    )

    dotenv_values = parse_dotenv(ROOT / ".env")
    if dotenv_values:
        missing_dotenv_keys = sorted(ENV_KEYS - set(dotenv_values))
        add(
            results,
            "WARN" if missing_dotenv_keys else "PASS",
            ".env",
            "missing setting names: " + ", ".join(missing_dotenv_keys)
            if missing_dotenv_keys
            else "present and structurally consistent",
        )
    else:
        add(results, "WARN", ".env", "not present; copy .env.example for local development")

    docker = shutil.which("docker")
    if not docker:
        add(
            results,
            "FAIL" if blocking_infra else "WARN",
            "Docker CLI",
            "not found on PATH; Docker checks are unavailable",
        )
    else:
        docker_version = command_version([docker, "--version"])
        add(results, "PASS", "Docker CLI", docker_version or "available")
        compose_version = command_version([docker, "compose", "version"])
        add(
            results,
            "PASS" if compose_version else ("FAIL" if blocking_infra else "WARN"),
            "Docker Compose v2",
            compose_version or "docker compose plugin is unavailable",
        )
        daemon_ok = command_ok([docker, "info"])
        add(
            results,
            "PASS" if daemon_ok else ("FAIL" if blocking_infra else "WARN"),
            "Docker daemon",
            "reachable" if daemon_ok else "unreachable; start Docker Desktop/WSL integration",
        )

    combined = {**dotenv_values, **os.environ}
    development_url = combined.get("DATABASE_URL", "")
    test_url = combined.get("TEST_DATABASE_URL", "")

    if mode == "development":
        if not development_url:
            add(results, "WARN", "DATABASE_URL", "not set; documented local default will be used")
            development_url = "postgresql+psycopg://local@127.0.0.1:5432/eventhub_ktpm"
        identity = database_identity(development_url)
        if identity is None:
            add(
                results,
                "FAIL",
                "Development database",
                "DATABASE_URL is not a valid PostgreSQL URL",
            )
        else:
            host, port, database = identity
            reachable = port_open(host, port)
            add(
                results,
                "PASS" if reachable else "FAIL",
                "Development database",
                f"{host}:{port}, database={database} is "
                + ("reachable" if reachable else "not reachable"),
            )
    elif mode == "postgres-test":
        if not test_url:
            add(results, "FAIL", "TEST_DATABASE_URL", "required in postgres-test mode")
        else:
            safe, detail = is_disposable_test_database(test_url, development_url)
            add(results, "PASS" if safe else "FAIL", "Disposable test database", detail)
            identity = database_identity(test_url)
            if safe and identity is not None:
                host, port, database = identity
                reachable = port_open(host, port)
                add(
                    results,
                    "PASS" if reachable else "FAIL",
                    "Test PostgreSQL",
                    f"{host}:{port}, database={database} is "
                    + ("reachable" if reachable else "not reachable"),
                )
    else:
        add(results, "PASS", "API-only mode", "Docker and PostgreSQL are optional in this mode")

    if port_open("127.0.0.1", 8000):
        add(results, "WARN", "API port 8000", "already occupied")
    else:
        add(results, "PASS", "API port 8000", "available")

    environment = combined.get("ENVIRONMENT", "local").strip().lower()
    secret = combined.get("JWT_SECRET", "")
    if environment in {"prod", "production"} and len(secret) < 32:
        add(results, "FAIL", "Production JWT secret", "missing or shorter than 32 characters")
    elif not secret:
        add(results, "WARN", "JWT_SECRET", "not set; local development default will be used")
    else:
        add(results, "PASS", "JWT_SECRET", "present; value was not displayed")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("api-only", "development", "postgres-test"),
        default="development",
    )
    args = parser.parse_args()

    results = check_environment(args.mode)
    for result in results:
        print(f"[{result.level}] {result.check}: {result.detail}")
    failures = sum(result.level == "FAIL" for result in results)
    warnings = sum(result.level == "WARN" for result in results)
    print(f"Summary: {failures} FAIL, {warnings} WARN")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
