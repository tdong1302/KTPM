"""Enforces the layering rule from the course brief.

"Tầng nghiệp vụ không import framework web hay thư viện DB" - the business layer must not
import a web framework or a database library. Rather than trusting a convention, this test
parses every module under app/domain and app/application and fails the build on violation.
"""

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Packages that the pure layers are forbidden to depend on.
FORBIDDEN_ROOTS = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "psycopg2",
    "pydantic",
    "pydantic_settings",
    "jwt",
    "bcrypt",
    "httpx",
    "requests",
}

# Business layers may only reach for the standard library, their own layer, and the domain.
ALLOWED_FIRST_PARTY_PREFIXES = ("app.domain", "app.application")

PURE_LAYERS = ("app/domain", "app/application")


def _modules() -> list[Path]:
    files: list[Path] = []
    for layer in PURE_LAYERS:
        files.extend(sorted((PROJECT_ROOT / layer).rglob("*.py")))
    assert files, "no modules found in the pure layers; check the project layout"
    return files


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 means a relative import, which stays inside the same layer.
            if node.level == 0 and node.module:
                roots.add(node.module)
    return roots


@pytest.mark.parametrize("module_path", _modules(), ids=lambda p: str(p.name))
def test_pure_layer_has_no_framework_or_db_imports(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    offenders = {name for name in _imported_roots(tree) if name.split(".")[0] in FORBIDDEN_ROOTS}
    relative = module_path.relative_to(PROJECT_ROOT).as_posix()
    assert not offenders, (
        f"{relative} imports {sorted(offenders)}; the business layer must depend on "
        f"ports only (see app/application/ports.py)"
    )


@pytest.mark.parametrize("module_path", _modules(), ids=lambda p: str(p.name))
def test_pure_layer_only_depends_on_itself(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    offenders = {
        name
        for name in _imported_roots(tree)
        if name.startswith("app.") and not name.startswith(ALLOWED_FIRST_PARTY_PREFIXES)
    }
    relative = module_path.relative_to(PROJECT_ROOT).as_posix()
    assert not offenders, (
        f"{relative} imports {sorted(offenders)}; app.domain and app.application must not "
        f"depend on app.api or app.infrastructure"
    )


def test_domain_does_not_depend_on_application() -> None:
    """The dependency arrow points one way: application -> domain, never back."""
    offenders: dict[str, list[str]] = {}
    for module_path in sorted((PROJECT_ROOT / "app/domain").rglob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        bad = sorted(n for n in _imported_roots(tree) if n.startswith("app.application"))
        if bad:
            offenders[module_path.relative_to(PROJECT_ROOT).as_posix()] = bad
    assert not offenders, f"domain must not import the application layer: {offenders}"
