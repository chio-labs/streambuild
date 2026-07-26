"""Persistence helpers for reconcile execution."""

from __future__ import annotations

from dataclasses import asdict

from streambuild.clickhouse.metadata_state.main.build_metadata_state_insert_statements import (
    build_metadata_state_insert_statements,
)
from streambuild.clickhouse.metadata_state.main.render_metadata_state_statements import (
    render_metadata_state_statements,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement
from streambuild.compiler.actual_state._helpers.metadata import build_normalized_fingerprint
from streambuild.compiler.metadata_state.models import ObjectStateRecord
from streambuild.compiler.shared.models import DesiredMaterializedView, DesiredTable
from streambuild.executor.reconcile.models import ReconcilePreview, ReconcileResult
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def apply_reconcile(*, client: ClickHouseClient, preview: ReconcilePreview) -> ReconcileResult:
    """Persist reconciled object-state records."""

    ensure_metadata_tables(client=client, metadata_database=preview.database)
    statements: tuple[RenderedClickHouseStatement, ...] = build_metadata_state_insert_statements(
        database=preview.database,
        object_states=preview.eligible_records,
        deployments=(),
        deployment_watermarks=(),
        deployment_runtime_details=(),
        publish_events=(),
    )
    for statement in statements:
        if not statement.rows:
            continue
        client.insert_rows(table=insert_table_name(statement.sql), rows=statement.rows)
    return ReconcileResult(
        database=preview.database,
        reconcile_id=preview.reconcile_id,
        reconciled_records=preview.eligible_records,
        rejected_targets=preview.rejected_targets,
    )


def build_object_state_record(
    *,
    desired_object: DesiredTable | DesiredMaterializedView,
    reconcile_id: str,
    recorded_at: str,
) -> ObjectStateRecord:
    normalized_query: str | None = (
        desired_object.query if isinstance(desired_object, DesiredMaterializedView) else None
    )
    return ObjectStateRecord(
        deployment_id=reconcile_id,
        key=desired_object.key,
        normalized_fingerprint=build_normalized_fingerprint(asdict(desired_object.spec)),
        normalized_query=normalized_query,
        recorded_at=recorded_at,
    )


def insert_table_name(statement_sql: str) -> str:
    return statement_sql[len("INSERT INTO ") :].split(" ", 1)[0]


def ensure_metadata_tables(*, client: ClickHouseClient, metadata_database: str) -> None:
    client.command(f"CREATE DATABASE IF NOT EXISTS {metadata_database}")
    statements: tuple[RenderedClickHouseStatement, ...] = render_metadata_state_statements(
        metadata_database
    )
    for statement in statements:
        client.command(statement.sql)
