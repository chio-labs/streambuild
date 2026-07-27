"""Discovery entry point for SQL-native test files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from streambuild.compiler.macros.models import MacroContext, MacroRegistry
from streambuild.compiler.test_discovery._helpers.parsing import parse_sql_test_file
from streambuild.compiler.test_discovery.models import LoadedSqlTest


def discover_sql_tests(
    *,
    root: Path,
    contents_by_path: Mapping[Path, str] | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
) -> list[LoadedSqlTest]:
    """Discover and parse SQL-native test files under a project tests root."""

    if not root.exists():
        return []
    loaded_tests: list[LoadedSqlTest] = []
    file_path: Path
    for file_path in sorted(root.rglob("*.sql")):
        loaded_tests.extend(
            parse_sql_test_file(
                file_path=file_path,
                contents=None if contents_by_path is None else contents_by_path[file_path],
                macro_registry=macro_registry,
                macro_context=macro_context,
            )
        )
    return loaded_tests
