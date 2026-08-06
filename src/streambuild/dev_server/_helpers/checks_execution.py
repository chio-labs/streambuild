"""Run, persist, and recall audit/test outcomes for the UI."""

from __future__ import annotations

import json
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterCurrentQualityNode, AdapterInvocationRecord
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.testing.models import SqlTestCase
from streambuild.dev_server.exceptions import DevServerError
from streambuild.executor.auditing.main.execute_sql_audits import execute_sql_audits
from streambuild.executor.auditing.models import SqlAuditResult, SqlAuditRunResult
from streambuild.executor.auditing.types import AuditSeverity
from streambuild.executor.observability.main.build_definition_fingerprint import (
    build_definition_fingerprint,
)
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

_NEVER_RUN_STATUS: str = "never_run"
_SUCCEEDED_OUTCOME: str = "succeeded"
_FAILED_OUTCOME: str = "failed"
_PASSED_STATUS: str = "passed"
_WARNING_STATUS: str = "warning"
_FAILED_STATUS: str = "failed"
_ERROR_STATUS: str = "error"


def _audit_status(result: SqlAuditResult) -> str:
    if result.error_message is not None:
        return _ERROR_STATUS
    if result.passed:
        return _PASSED_STATUS
    if str(result.severity) == AuditSeverity.WARNING:
        return _WARNING_STATUS
    return _FAILED_STATUS


def _test_status(result: SqlTestExecutionResult) -> str:
    if result.error_message is not None:
        return _ERROR_STATUS
    return _PASSED_STATUS if result.passed else _FAILED_STATUS


def _recorded_target_payloads(result: SqlTestExecutionResult) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    target: SqlTestTargetExecutionResult
    for target in result.target_results:
        payloads.append(
            {
                "target_model_name": target.target_model_name,
                "passed": target.passed,
                "columns": list(target.column_names),
                "missing_rows": [list(item) for item in target.missing_rows[:5]],
                "unexpected_rows": [list(item) for item in target.unexpected_rows[:5]],
            }
        )
    return payloads


def run_one_audit(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    name: str,
    project_dir: Path,
    database: str,
) -> dict[str, object]:
    """Execute one named audit and record its outcome like a CLI run would."""

    audit: LoadedSqlAudit | None = _audit_by_name(analysis=analysis, name=name)
    if audit is None:
        raise DevServerError(f"Unknown audit '{name}'")
    started: tuple[str, str, int] = start_invocation()
    run: SqlAuditRunResult = execute_sql_audits(
        loaded_audits=(audit,),
        resolver=_model_resolver(analysis),
        client=connection,
        dialect=analysis.adapter_profile.sql_analysis_dialect,
    )
    result: SqlAuditResult = run.audit_results[0]
    _persist_audit_observation(
        connection=connection,
        database=database,
        project_dir=project_dir,
        started=started,
        audit=audit,
        result=result,
    )
    return {
        "name": name,
        "kind": "audit",
        "passed": result.passed,
        "severity": result.severity,
        "failingRowCount": result.failing_row_count,
        "sampleColumns": list(result.sample_column_names),
        "sampleRows": [list(row) for row in result.sample_rows],
        "errorMessage": result.error_message,
    }


def run_one_test(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    name: str,
    project_dir: Path,
    database: str,
) -> dict[str, object]:
    """Execute one named SQL test and record its outcome like a CLI run would."""

    test_case: SqlTestCase | None = _test_by_name(analysis=analysis, name=name)
    if test_case is None:
        raise DevServerError(f"Unknown test '{name}'")
    started: tuple[str, str, int] = start_invocation()
    results: tuple[SqlTestExecutionResult, ...] = execute_sql_tests(
        test_cases=(test_case,), client=connection
    )
    result: SqlTestExecutionResult = results[0]
    _persist_test_observation(
        connection=connection,
        database=database,
        project_dir=project_dir,
        started=started,
        test_case=test_case,
        result=result,
    )
    return {
        "name": name,
        "kind": "test",
        "passed": result.passed,
        "targets": [_target_payload(target) for target in result.target_results],
        "errorMessage": result.error_message,
    }


def build_checks_status_payload(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    database: str,
    project_dir: Path,
) -> list[dict[str, object]]:
    """Last-known outcome per audit/test from the observability tables."""

    name_by_identity: dict[tuple[str, str], str] = {}
    nodes: list[AdapterCurrentQualityNode] = []
    for audit in analysis.compiled_project.audits:
        identity: str = build_quality_node_identity(
            project_dir=project_dir, file_path=audit.file_path, node_index=audit.audit_index
        )
        name_by_identity[("audit", identity)] = audit.name or audit.file_path.stem
        nodes.append(
            AdapterCurrentQualityNode(
                node_kind="audit",
                node_identity=identity,
                definition_fingerprint=build_definition_fingerprint(
                    definition=audit.query, severity=audit.severity
                ),
            )
        )
    for test_case in analysis.compiled_project.test_cases:
        identity = build_quality_node_identity(
            project_dir=project_dir, file_path=test_case.file_path, node_index=test_case.test_index
        )
        name_by_identity[("test", identity)] = test_case.name or test_case.file_path.stem
        nodes.append(
            AdapterCurrentQualityNode(
                node_kind="test",
                node_identity=identity,
                definition_fingerprint=build_definition_fingerprint(
                    definition=test_case.query, severity=None
                ),
            )
        )
    query: str = connection.render_latest_node_status_query(
        database=database,
        project_identity=str(project_dir.resolve()),
        target_identity=database,
        nodes=tuple(nodes),
    )
    statuses: list[dict[str, object]] = []
    for row in connection.query(query).named_rows():
        statuses.append(_status_row_payload(row=dict(row), name_by_identity=name_by_identity))
    return statuses


def _status_row_payload(
    *, row: dict[str, object], name_by_identity: dict[tuple[str, str], str]
) -> dict[str, object]:
    kind: str = str(row["node_kind"])
    identity: str = str(row["node_identity"])
    status: str = str(row["current_status"])
    recorded: bool = status != _NEVER_RUN_STATUS
    return {
        "kind": kind,
        "name": name_by_identity.get((kind, identity), identity),
        "status": status,
        "severity": row["severity"],
        "failureCount": int(str(row["failure_count"])) if recorded else 0,
        "completedAt": str(row["completed_at"]) if recorded else None,
        "payload": _parsed_payload(row["payload_json"]) if recorded else None,
        "errorMessage": row["error_message"],
    }


def _parsed_payload(payload_json: object) -> dict[str, object] | None:
    try:
        parsed: object = json.loads(str(payload_json))
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _persist_audit_observation(
    *,
    connection: AdapterConnection,
    database: str,
    project_dir: Path,
    started: tuple[str, str, int],
    audit: LoadedSqlAudit,
    result: SqlAuditResult,
) -> None:
    hard_failure: bool = (result.error_message is not None or not result.passed) and str(
        result.severity
    ) != AuditSeverity.WARNING
    invocation: AdapterInvocationRecord = build_invocation_record(
        started=started,
        terminal=TerminalInvocation(
            project_dir=project_dir,
            target_identity=database,
            command="audit",
            mode=None,
            outcome=_FAILED_OUTCOME if hard_failure else _SUCCEEDED_OUTCOME,
            exit_code=1 if hard_failure else 0,
            materialized_outcome=None,
            deployment_id=None,
            workflow_id=None,
            selected_node_count=1,
            error_message=result.error_message,
            summary={"source": "dev_server"},
        ),
    )
    status: str = _audit_status(result)
    persist_terminal_observations(
        client=connection,
        database=database,
        invocation=invocation,
        node_results=(
            build_node_result_record(
                invocation=invocation,
                node_kind="audit",
                node_identity=build_quality_node_identity(
                    project_dir=project_dir,
                    file_path=audit.file_path,
                    node_index=audit.audit_index,
                ),
                definition=audit.query,
                status=status,
                severity=result.severity,
                failure_count=result.failing_row_count,
                payload={
                    "sample_column_names": list(result.sample_column_names),
                    "sample_rows": [list(item) for item in result.sample_rows[:5]],
                },
                error_message=result.error_message,
            ),
        ),
    )


def _persist_test_observation(
    *,
    connection: AdapterConnection,
    database: str,
    project_dir: Path,
    started: tuple[str, str, int],
    test_case: SqlTestCase,
    result: SqlTestExecutionResult,
) -> None:
    missing_count: int = sum(len(target.missing_rows) for target in result.target_results)
    unexpected_count: int = sum(len(target.unexpected_rows) for target in result.target_results)
    failed: bool = result.error_message is not None or not result.passed
    invocation: AdapterInvocationRecord = build_invocation_record(
        started=started,
        terminal=TerminalInvocation(
            project_dir=project_dir,
            target_identity=database,
            command="test",
            mode=None,
            outcome=_FAILED_OUTCOME if failed else _SUCCEEDED_OUTCOME,
            exit_code=1 if failed else 0,
            materialized_outcome=None,
            deployment_id=None,
            workflow_id=None,
            selected_node_count=1,
            error_message=result.error_message,
            summary={"source": "dev_server"},
        ),
    )
    status: str = _test_status(result)
    persist_terminal_observations(
        client=connection,
        database=database,
        invocation=invocation,
        node_results=(
            build_node_result_record(
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
                failure_count=missing_count
                + unexpected_count
                + int(result.error_message is not None),
                payload={
                    "missing_count": missing_count,
                    "unexpected_count": unexpected_count,
                    "targets": _recorded_target_payloads(result),
                },
                error_message=result.error_message,
            ),
        ),
    )


def _target_payload(target: SqlTestTargetExecutionResult) -> dict[str, object]:
    return {
        "targetModelName": target.target_model_name,
        "passed": target.passed,
        "columns": list(target.column_names),
        "missingRows": [list(row) for row in target.missing_rows],
        "unexpectedRows": [list(row) for row in target.unexpected_rows],
    }


def _audit_by_name(*, analysis: CompileAnalysis, name: str) -> LoadedSqlAudit | None:
    for audit in analysis.compiled_project.audits:
        if (audit.name or audit.file_path.stem) == name:
            return audit
    return None


def _test_by_name(*, analysis: CompileAnalysis, name: str) -> SqlTestCase | None:
    for test_case in analysis.compiled_project.test_cases:
        if (test_case.name or test_case.file_path.stem) == name:
            return test_case
    return None


def _model_resolver(analysis: CompileAnalysis) -> dict[str, str]:
    resolver: dict[str, str] = {}
    for key, relation in analysis.realized_project.relation_name_by_logical_key.items():
        if key.resource_type == LogicalResourceType.MODEL:
            resolver[key.name] = relation
    return resolver
