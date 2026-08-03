"""Run one audit or test read-only and shape its result for the UI."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.testing.models import SqlTestCase
from streambuild.dev_server.exceptions import DevServerError
from streambuild.executor.auditing.main.execute_sql_audits import execute_sql_audits
from streambuild.executor.auditing.models import SqlAuditResult, SqlAuditRunResult
from streambuild.executor.testing.main.execute_sql_tests import execute_sql_tests
from streambuild.executor.testing.models import (
    SqlTestExecutionResult,
    SqlTestTargetExecutionResult,
)


def run_one_audit(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    name: str,
) -> dict[str, object]:
    """Execute one named audit through the read-only query path."""

    audit: LoadedSqlAudit | None = _audit_by_name(analysis=analysis, name=name)
    if audit is None:
        raise DevServerError(f"Unknown audit '{name}'")
    run: SqlAuditRunResult = execute_sql_audits(
        loaded_audits=(audit,),
        resolver=_model_resolver(analysis),
        client=connection,
        dialect=analysis.adapter_profile.sql_analysis_dialect,
    )
    result: SqlAuditResult = run.audit_results[0]
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
) -> dict[str, object]:
    """Execute one named SQL test through the read-only query path."""

    test_case: SqlTestCase | None = _test_by_name(analysis=analysis, name=name)
    if test_case is None:
        raise DevServerError(f"Unknown test '{name}'")
    results: tuple[SqlTestExecutionResult, ...] = execute_sql_tests(
        test_cases=(test_case,), client=connection
    )
    result: SqlTestExecutionResult = results[0]
    return {
        "name": name,
        "kind": "test",
        "passed": result.passed,
        "targets": [_target_payload(target) for target in result.target_results],
        "errorMessage": result.error_message,
    }


def _target_payload(target: SqlTestTargetExecutionResult) -> dict[str, object]:
    return {
        "targetModelName": target.target_model_name,
        "passed": target.passed,
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
