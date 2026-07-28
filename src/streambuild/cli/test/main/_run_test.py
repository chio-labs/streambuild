"""CLI command for executing SQL-native model tests."""

from __future__ import annotations

from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.test._helpers.rendering import render_sql_test_results
from streambuild.cli.test._helpers.runtime_artifacts import write_test_runtime_target
from streambuild.cli.test._helpers.selection import select_loaded_sql_tests
from streambuild.cli.test.constants import DEFAULT_TARGET_DIRECTORY_NAME
from streambuild.compiler.compile.models import CompiledPipeline, CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.test_discovery.models import LoadedSqlTest
from streambuild.compiler.testing.models import SqlTestCase
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
    target_dir: Path | None = None,
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
    write_test_runtime_target(
        target_dir=target_dir or (resolved_project_dir / DEFAULT_TARGET_DIRECTORY_NAME),
        test_cases=test_cases,
        results=results,
    )
    rendered_output: str = render_sql_test_results(
        results=results,
        project_dir=resolved_project_dir,
        verbose=verbose,
    )
    print(rendered_output)
    failed_count: int = sum(1 for result in results if not result.passed)
    if failed_count:
        return 1
    return 0
