"""Entry point for executing SQL audits against ClickHouse."""

from __future__ import annotations

from collections.abc import Mapping

from streambuild.compiler.compile.main.replace_refs import replace_refs
from streambuild.compiler.shared.models import LoadedSqlAudit
from streambuild.executor.auditing.constants import AUDIT_SAMPLE_LIMIT
from streambuild.executor.auditing.exceptions import AuditExecutionError
from streambuild.executor.auditing.models import SqlAuditResult, SqlAuditRunResult
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseQueryResult


def execute_sql_audits(
    *,
    loaded_audits: tuple[LoadedSqlAudit, ...],
    resolver: Mapping[str, str],
    client: ClickHouseClient,
) -> SqlAuditRunResult:
    """Execute discovered SQL audits with resolved model refs."""

    return SqlAuditRunResult(
        audit_results=tuple(
            _execute_single_sql_audit(
                loaded_audit=loaded_audit,
                resolver=resolver,
                client=client,
            )
            for loaded_audit in loaded_audits
        )
    )


def _execute_single_sql_audit(
    *,
    loaded_audit: LoadedSqlAudit,
    resolver: Mapping[str, str],
    client: ClickHouseClient,
) -> SqlAuditResult:
    resolved_query: str = replace_refs(sql=loaded_audit.query, resolver=dict(resolver))
    failing_row_count: int = _query_failing_row_count(query=resolved_query, client=client)
    sample_column_names: tuple[str, ...] = ()
    sample_rows: tuple[tuple[object, ...], ...] = ()
    if failing_row_count:
        sample_result: ClickHouseQueryResult = client.query(
            f"SELECT * FROM ({resolved_query}) AS __streambuild_audit LIMIT {AUDIT_SAMPLE_LIMIT}"
        )
        sample_column_names = sample_result.column_names
        sample_rows = sample_result.rows
    return SqlAuditResult(
        file_path=loaded_audit.file_path,
        referenced_model_names=loaded_audit.referenced_model_names,
        severity=loaded_audit.severity,
        passed=failing_row_count == 0,
        failing_row_count=failing_row_count,
        sample_column_names=sample_column_names,
        sample_rows=sample_rows,
        description=loaded_audit.description,
        name=loaded_audit.name,
    )


def _query_failing_row_count(*, query: str, client: ClickHouseClient) -> int:
    result: ClickHouseQueryResult = client.query(
        f"SELECT count() AS value FROM ({query}) AS __streambuild_audit"
    )
    if not result.rows:
        raise AuditExecutionError("Expected a count row from SQL audit execution")
    count_value: object = result.rows[0][0]
    if not isinstance(count_value, (int, float, str)):
        raise AuditExecutionError("SQL audit count query returned a non-numeric row count")
    return int(count_value)
