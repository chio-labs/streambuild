"""CLI command for executing SQL-native model tests."""

from __future__ import annotations

from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.test._helpers.rendering import render_sql_test_results
from streambuild.cli.test._helpers.selection import select_loaded_sql_tests
from streambuild.compiler.compile.models import CompiledPipeline, CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.test_discovery.models import LoadedSqlTest, SqlTestCase
from streambuild.executor.testing.main.execute_sql_tests import execute_sql_tests
from streambuild.executor.testing.models import SqlTestExecutionResult


def run_test(
    *,
    pipelines_root: Path,
    project_dir: Path | None,
    selectors: tuple[str, ...],
    paths: tuple[Path, ...],
    verbose: bool,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Discover, assemble, and execute SQL-native tests for a project."""

    resolved_project_dir: Path = project_dir or pipelines_root.parent
    analysis: CompileAnalysis = analyze_project(
        pipelines_root=pipelines_root,
        loaded_project=loaded_project,
        adapter_profile=adapter_profile,
    )
    compiled_pipelines: tuple[CompiledPipeline, ...] = analysis.compiled_project.pipelines
    loaded_tests: tuple[LoadedSqlTest, ...] = analysis.compiled_project.tests
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
    selected_test_keys: frozenset[tuple[Path, int]] = frozenset(
        (loaded_test.file_path, loaded_test.test_index) for loaded_test in selected_tests
    )
    test_cases: tuple[SqlTestCase, ...] = tuple(
        test_case
        for test_case in analysis.compiled_project.test_cases
        if (test_case.file_path, test_case.test_index) in selected_test_keys
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
