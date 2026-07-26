"""Metadata persistence for publish execution."""

from datetime import UTC, datetime

from streambuild.clickhouse.metadata_state._helpers.statements.main import (
    build_metadata_state_insert_statements,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement
from streambuild.compiler.metadata_state.main import build_metadata_state
from streambuild.compiler.metadata_state.models import MetadataState, PublishEventRecord
from streambuild.executor.backfill._helpers.metadata import ensure_metadata_tables
from streambuild.executor.publish.constants import PUBLISH_HISTORY_TABLE_NAME
from streambuild.executor.publish.models import PublishedView
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def persist_publish_event(
    *,
    client: ClickHouseClient,
    metadata_database: str,
    deployment_id: str,
    published_views: tuple[PublishedView, ...],
) -> None:
    """Persist one publish history event for a deployment."""

    ensure_metadata_tables(client=client, metadata_database=metadata_database)
    published_at: str = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    metadata_state: MetadataState = build_metadata_state(
        object_states=(),
        deployments=(),
        deployment_watermarks=(),
        deployment_runtime_details=(),
        publish_events=(
            PublishEventRecord(
                deployment_id=deployment_id,
                published_at=published_at,
                logical_view_names=tuple(view.view_name for view in published_views),
            ),
        ),
    )
    insert_statements: tuple[RenderedClickHouseStatement, ...] = (
        build_metadata_state_insert_statements(
            database=metadata_database,
            object_states=metadata_state.object_states,
            deployments=metadata_state.deployments,
            deployment_watermarks=metadata_state.deployment_watermarks,
            deployment_runtime_details=metadata_state.deployment_runtime_details,
            publish_events=metadata_state.publish_events,
        )
    )
    statement: RenderedClickHouseStatement
    for statement in insert_statements:
        if not statement.rows:
            continue
        if PUBLISH_HISTORY_TABLE_NAME not in statement.sql:
            continue
        client.insert_rows(table=_insert_table_name(statement.sql), rows=statement.rows)


def _insert_table_name(statement_sql: str) -> str:
    statement_prefix: str = "INSERT INTO "
    remainder: str = statement_sql[len(statement_prefix) :]
    return remainder.split(" ", 1)[0]
