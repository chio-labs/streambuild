"""CLI command for executing SQL-native model tests."""

from __future__ import annotations

from pathlib import Path

from streambuild.cli.commands.main.test._helpers.rendering import render_sql_test_results
from streambuild.cli.commands.main.test._helpers.selection import select_loaded_sql_tests
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery._helpers.testing.main import discover_sql_tests
from streambuild.compiler.discovery.main import discover_pipelines
from streambuild.compiler.shared.models import LoadedPipeline, LoadedSqlTest
from streambuild.compiler.testing.main import build_sql_test_cases
from streambuild.compiler.testing.models import SqlTestCase
from streambuild.executor.testing.main import execute_sql_tests
from streambuild.executor.testing.models import SqlTestExecutionResult
from streambuild.integrations.clickhouse.client import ClickHouseClient


def run_test(
    pipelines_root: Path,
    *,
    project_dir: Path | None,
    selectors: tuple[str, ...],
    paths: tuple[Path, ...],
    verbose: bool,
    client: ClickHouseClient,
) -> int:
    """Discover, assemble, and execute SQL-native tests for a project."""

    resolved_project_dir: Path = project_dir or pipelines_root.parent
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
    compiled_pipelines: tuple[CompiledPipeline, ...] = tuple(
        compile_pipeline(loaded_pipeline) for loaded_pipeline in loaded_pipelines
    )
    loaded_tests: tuple[LoadedSqlTest, ...] = tuple(
        discover_sql_tests(resolved_project_dir / "tests")
    )
    selected_tests: tuple[LoadedSqlTest, ...] = select_loaded_sql_tests(
        loaded_tests=loaded_tests,
        compiled_pipelines=compiled_pipelines,
        selectors=selectors,
        paths=paths,
        project_dir=resolved_project_dir,
    )
    if not selected_tests:
        print("No SQL tests found.")
        return 0
    test_cases: tuple[SqlTestCase, ...] = build_sql_test_cases(
        loaded_tests=selected_tests,
        compiled_pipelines=compiled_pipelines,
    )
    results: tuple[SqlTestExecutionResult, ...] = execute_sql_tests(
        test_cases=test_cases,
        client=client,
    )
    rendered_output: str = render_sql_test_results(
        results=results,
        project_dir=resolved_project_dir,
        verbose=verbose,
    )
    print(rendered_output)
    passed_count: int = sum(1 for result in results if result.passed)
    failed_count: int = len(results) - passed_count
    if failed_count:
        return 1
    return 0
