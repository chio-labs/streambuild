"""CLI command for executing SQL-native model tests."""

from __future__ import annotations

from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterInvocationRecord, AdapterNodeResultRecord
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
from streambuild.executor.observability.main.build_invocation_record import (
    build_invocation_record,
)
from streambuild.executor.observability.main.build_node_result_record import (
    build_node_result_record,
)
from streambuild.executor.observability.main.build_quality_node_identity import (
    build_quality_node_identity,
)
from streambuild.executor.observability.main.persist_terminal_observations import (
    persist_terminal_observations,
)
from streambuild.executor.observability.main.start_invocation import start_invocation
from streambuild.executor.observability.models import TerminalInvocation
from streambuild.executor.testing.main.execute_sql_tests import execute_sql_tests
from streambuild.executor.testing.models import (
    SqlTestExecutionResult,
    SqlTestTargetExecutionResult,
)


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
    database: str = "",
) -> int:
    """Discover, assemble, and execute SQL-native tests for a project."""

    started: tuple[str, str, int] = start_invocation()
    resolved_project_dir: Path = project_dir or pipelines_root.parent
    selected_node_count = 0
    try:
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
        selected_node_count = len(selected_tests)
        if not selected_tests:
            print("No SQL tests found.")
            invocation: AdapterInvocationRecord = build_invocation_record(
                started=started,
                terminal=TerminalInvocation(
                    project_dir=resolved_project_dir,
                    target_identity=database,
                    command="test",
                    mode=None,
                    outcome="succeeded",
                    exit_code=0,
                    materialized_outcome=None,
                    deployment_id=None,
                    workflow_id=None,
                    selected_node_count=0,
                    error_message=None,
                    summary={"failed_count": 0},
                ),
            )
            _ = persist_terminal_observations(
                client=client,
                database=database,
                invocation=invocation,
                node_results=(),
            )
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
    except Exception as error:
        failed_invocation: AdapterInvocationRecord = build_invocation_record(
            started=started,
            terminal=TerminalInvocation(
                project_dir=resolved_project_dir,
                target_identity=database,
                command="test",
                mode=None,
                outcome="failed",
                exit_code=1,
                materialized_outcome=None,
                deployment_id=None,
                workflow_id=None,
                selected_node_count=selected_node_count,
                error_message=str(error),
                summary={"failed_before_results": True},
            ),
        )
        _ = persist_terminal_observations(
            client=client,
            database=database,
            invocation=failed_invocation,
            node_results=(),
        )
        raise
    failed_count: int = sum(1 for result in results if not result.passed)
    exit_code: int = 1 if failed_count else 0
    invocation = build_invocation_record(
        started=started,
        terminal=TerminalInvocation(
            project_dir=resolved_project_dir,
            target_identity=database,
            command="test",
            mode=None,
            outcome="failed" if exit_code else "succeeded",
            exit_code=exit_code,
            materialized_outcome=None,
            deployment_id=None,
            workflow_id=None,
            selected_node_count=len(test_cases),
            error_message=None,
            summary={"failed_count": failed_count},
        ),
    )
    node_results: tuple[AdapterNodeResultRecord, ...] = tuple(
        _test_node_result(
            invocation=invocation,
            test_case=test_case,
            result=result,
            project_dir=resolved_project_dir,
        )
        for test_case, result in zip(test_cases, results, strict=True)
    )
    _ = persist_terminal_observations(
        client=client,
        database=database,
        invocation=invocation,
        node_results=node_results,
    )
    return exit_code


def _test_node_result(
    *,
    invocation: AdapterInvocationRecord,
    test_case: SqlTestCase,
    result: SqlTestExecutionResult,
    project_dir: Path,
) -> AdapterNodeResultRecord:
    missing_count: int = sum(len(target.missing_rows) for target in result.target_results)
    unexpected_count: int = sum(len(target.unexpected_rows) for target in result.target_results)
    status: str = (
        "error" if result.error_message is not None else ("passed" if result.passed else "failed")
    )
    return build_node_result_record(
        invocation=invocation,
        node_kind="test",
        node_identity=build_quality_node_identity(
            project_dir=project_dir,
            file_path=test_case.file_path,
            node_index=test_case.test_index,
        ),
        definition=test_case.query,
        status=status,
        severity=None,
        failure_count=missing_count + unexpected_count + int(result.error_message is not None),
        payload={
            "missing_count": missing_count,
            "unexpected_count": unexpected_count,
            "targets": _target_payloads(result),
        },
        error_message=result.error_message,
    )


def _target_payloads(result: SqlTestExecutionResult) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    target: SqlTestTargetExecutionResult
    for target in result.target_results:
        payloads.append(
            {
                "name": target.target_model_name,
                "missing_rows": [list(row) for row in target.missing_rows[:5]],
                "unexpected_rows": [list(row) for row in target.unexpected_rows[:5]],
            }
        )
    return payloads
