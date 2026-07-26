"""Discovery entry point for SQL-native test files."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.test_discovery._helpers.parsing import parse_sql_test_file
from streambuild.compiler.test_discovery.models import LoadedSqlTest


def discover_sql_tests(root: Path) -> list[LoadedSqlTest]:
    """Discover and parse SQL-native test files under a project tests root."""

    if not root.exists():
        return []
    loaded_tests: list[LoadedSqlTest] = []
    file_path: Path
    for file_path in sorted(root.rglob("*.sql")):
        loaded_tests.extend(parse_sql_test_file(file_path))
    return loaded_tests
