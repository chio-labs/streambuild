"""Migrate and persist StreamBuild metadata in ClickHouse."""

import json
from hashlib import sha256
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME,
    METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME,
    METADATA_INVOCATIONS_TABLE_NAME,
    METADATA_NODE_RESULTS_TABLE_NAME,
    METADATA_OBJECT_STATE_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
    METADATA_SCHEMA_VERSIONS_TABLE_NAME,
    REPLAY_VALUE_KIND_INTEGER,
    REPLAY_VALUE_KIND_TIMESTAMP,
    VIRTUAL_OBJECT_STATE_KIND_DEPLOYMENT,
)
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterCurrentQualityNode,
    AdapterDeploymentRecord,
    AdapterDeploymentWatermarkRecord,
    AdapterInvocationRecord,
    AdapterMetadataState,
    AdapterNodeResultRecord,
    AdapterObjectStateRecord,
    AdapterOwnershipRecord,
    AdapterPublishEventRecord,
    AdapterQueryResult,
    AdapterReplayCoverageRange,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.adapters.clickhouse.constants import (
    EMPTY_DEFAULT_EXPRESSIONS,
    OWNERSHIP_EVENT_ROW_LENGTH,
    OWNERSHIP_RANGE_ROW_LENGTH,
    OWNERSHIP_TABLE_EXISTS_QUERY,
)
from streambuild.adapters.clickhouse.models import ClickHouseMetadataStatement

_CURRENT_STATE_SCHEMA_VERSION: int = 1
_BOUNDARY_PART_COUNT: int = 2


def render_clickhouse_metadata_migration_statements(database: str) -> tuple[str, ...]:
    """Render the current additive ClickHouse metadata migration."""

    return (
        _render_object_state_table(database),
        _render_deployments_table(database),
        _render_deployment_watermarks_table(database),
        _render_publish_history_table(database),
        _render_direct_replay_ranges_table(database),
        _render_direct_target_events_table(database),
        _render_invocations_table(database),
        _render_node_results_table(database),
    )


def render_clickhouse_metadata_migration_workflow(database: str) -> tuple[str, ...]:
    """Render the complete idempotent metadata migration as executable SQL."""

    migration_statements: tuple[str, ...] = render_clickhouse_metadata_migration_statements(
        database
    )
    return (
        f"CREATE DATABASE IF NOT EXISTS {database};",
        _terminate_sql(_render_schema_versions_table(database)),
        *tuple(_terminate_sql(statement) for statement in migration_statements),
        (
            f"INSERT INTO {database}.{METADATA_SCHEMA_VERSIONS_TABLE_NAME} "
            "(version, applied_at) "
            f"SELECT {_CURRENT_STATE_SCHEMA_VERSION}, now64(3, 'UTC') "
            "WHERE NOT EXISTS ("
            f"SELECT 1 FROM {database}.{METADATA_SCHEMA_VERSIONS_TABLE_NAME} "
            f"WHERE version = {_CURRENT_STATE_SCHEMA_VERSION});"
        ),
    )


def build_clickhouse_metadata_insert_statements(
    *, database: str, state: AdapterMetadataState
) -> tuple[ClickHouseMetadataStatement, ...]:
    """Build ClickHouse inserts for adapter-neutral metadata records."""

    return (
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_OBJECT_STATE_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_OBJECT_STATE_TABLE_NAME} "
                "(state_id, observation_id, state_kind, deployment_id, logical_database_name, "
                "logical_object_type, logical_object_name, physical_database_name, "
                "physical_relation_name, logical_model_database, logical_model_name, "
                "is_selected_root, object_fingerprint, canonical_query, observed_at) VALUES"
            ),
            rows=tuple(_object_state_row(record) for record in state.object_states),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_DEPLOYMENTS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_DEPLOYMENTS_TABLE_NAME} "
                "(deployment_id, workflow_fingerprint, replay_lineage_mode, boundary_time, "
                "created_at, tool_version) VALUES"
            ),
            rows=tuple(
                _deployment_row(record)
                for record in state.deployments
                if record.boundary_time is not None
            ),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} "
                "(deployment_id, root_database_name, root_object_type, root_object_name, "
                "anchor_database_name, anchor_object_type, anchor_object_name, boundary_kind, "
                "value_kind, partition_value, lower_value, cutoff_value, cutoff_inclusive, "
                "captured_at) VALUES"
            ),
            rows=tuple(_watermark_row(record) for record in state.deployment_watermarks),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME} "
                "(publication_id, deployment_id, logical_database_name, logical_view_name, "
                "physical_database_name, physical_relation_name, published_at) VALUES"
            ),
            rows=_publish_rows_for_records(state.publish_events),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_INVOCATIONS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_INVOCATIONS_TABLE_NAME} "
                "(invocation_id, project_identity, target_identity, command, mode, outcome, "
                "exit_code, materialized_outcome, deployment_id, workflow_id, "
                "selected_node_count, started_at, completed_at, duration_ms, error_message, "
                "summary_json, tool_version) VALUES"
            ),
            rows=tuple(_invocation_row(record) for record in state.invocations),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_NODE_RESULTS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_NODE_RESULTS_TABLE_NAME} "
                "(result_id, invocation_id, node_kind, node_identity, definition_fingerprint, "
                "target_identity, status, severity, failure_count, completed_at, payload_json, "
                "error_message) VALUES"
            ),
            rows=tuple(_node_result_row(record) for record in state.node_results),
        ),
    )


def render_clickhouse_metadata_state(
    *, database: str, state: AdapterMetadataState
) -> tuple[str, ...]:
    """Render metadata rows as exact manually executable ClickHouse inserts."""

    statements: tuple[ClickHouseMetadataStatement, ...] = (
        build_clickhouse_metadata_insert_statements(
            database=database,
            state=state,
        )
    )
    return tuple(_render_insert_statement(statement) for statement in statements if statement.rows)


def _render_schema_versions_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_SCHEMA_VERSIONS_TABLE_NAME} (\n"
        "    version UInt64,\n"
        "    applied_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (version)"
    )


def _render_object_state_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_OBJECT_STATE_TABLE_NAME} (\n"
        "    state_id String,\n"
        "    observation_id String,\n"
        "    state_kind LowCardinality(String),\n"
        "    deployment_id Nullable(String),\n"
        "    logical_database_name Nullable(String),\n"
        "    logical_object_type String,\n"
        "    logical_object_name String,\n"
        "    physical_database_name Nullable(String),\n"
        "    physical_relation_name Nullable(String),\n"
        "    logical_model_database Nullable(String),\n"
        "    logical_model_name Nullable(String),\n"
        "    is_selected_root Bool,\n"
        "    object_fingerprint String,\n"
        "    canonical_query Nullable(String),\n"
        "    observed_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (state_kind, state_id, logical_object_type, logical_object_name)"
    )


def _render_deployments_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_DEPLOYMENTS_TABLE_NAME} (\n"
        "    deployment_id String,\n"
        "    workflow_fingerprint String,\n"
        "    replay_lineage_mode String,\n"
        "    boundary_time DateTime64(3, 'UTC'),\n"
        "    created_at DateTime64(3, 'UTC'),\n"
        "    tool_version String\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (deployment_id)"
    )


def _render_deployment_watermarks_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} (\n"
        "    deployment_id String,\n"
        "    root_database_name Nullable(String),\n"
        "    root_object_type String,\n"
        "    root_object_name String,\n"
        "    anchor_database_name Nullable(String),\n"
        "    anchor_object_type String,\n"
        "    anchor_object_name String,\n"
        "    boundary_kind LowCardinality(String),\n"
        "    value_kind LowCardinality(String),\n"
        "    partition_value Nullable(String),\n"
        "    lower_value Nullable(String),\n"
        "    cutoff_value String,\n"
        "    cutoff_inclusive Bool,\n"
        "    captured_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (deployment_id, root_object_type, root_object_name, boundary_kind, "
        "ifNull(partition_value, ''))"
    )


def _render_publish_history_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME} (\n"
        "    publication_id String,\n"
        "    deployment_id String,\n"
        "    logical_database_name String,\n"
        "    logical_view_name String,\n"
        "    physical_database_name String,\n"
        "    physical_relation_name String,\n"
        "    published_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (publication_id, logical_database_name, logical_view_name)"
    )


def _render_direct_replay_ranges_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} (\n"
        "    replay_set_id String,\n"
        "    target_database_name String,\n"
        "    logical_model_database Nullable(String),\n"
        "    logical_model_name String,\n"
        "    range_present Bool,\n"
        "    driving_input_relation_name Nullable(String),\n"
        "    replay_boundary_mode Nullable(String),\n"
        "    partition_value Nullable(String),\n"
        "    source_partition_column_name Nullable(String),\n"
        "    source_position_column_name Nullable(String),\n"
        "    source_timestamp_column_name Nullable(String),\n"
        "    lower_value Nullable(String),\n"
        "    upper_value Nullable(String),\n"
        "    replay_cutoff_value Nullable(String),\n"
        "    captured_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (replay_set_id, range_present)"
    )


def _render_direct_target_events_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} (\n"
        "    event_id String,\n"
        "    workflow_id String,\n"
        "    event_kind LowCardinality(String),\n"
        "    database_name String,\n"
        "    relation_name String,\n"
        "    resource_kind String,\n"
        "    logical_model_database Nullable(String),\n"
        "    logical_model_name String,\n"
        "    tool_version String,\n"
        "    replay_set_id Nullable(String),\n"
        "    recorded_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (database_name, relation_name, recorded_at, event_id)"
    )


def _render_invocations_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_INVOCATIONS_TABLE_NAME} (\n"
        "    invocation_id String,\n"
        "    project_identity String,\n"
        "    target_identity String,\n"
        "    command LowCardinality(String),\n"
        "    mode Nullable(String),\n"
        "    outcome LowCardinality(String),\n"
        "    exit_code Int32,\n"
        "    materialized_outcome Nullable(String),\n"
        "    deployment_id Nullable(String),\n"
        "    workflow_id Nullable(String),\n"
        "    selected_node_count UInt64,\n"
        "    started_at DateTime64(3, 'UTC'),\n"
        "    completed_at DateTime64(3, 'UTC'),\n"
        "    duration_ms UInt64,\n"
        "    error_message Nullable(String),\n"
        "    summary_json String,\n"
        "    tool_version String\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (project_identity, target_identity, completed_at, invocation_id)"
    )


def _render_node_results_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_NODE_RESULTS_TABLE_NAME} (\n"
        "    result_id String,\n"
        "    invocation_id String,\n"
        "    node_kind LowCardinality(String),\n"
        "    node_identity String,\n"
        "    definition_fingerprint String,\n"
        "    target_identity String,\n"
        "    status LowCardinality(String),\n"
        "    severity Nullable(String),\n"
        "    failure_count UInt64,\n"
        "    completed_at DateTime64(3, 'UTC'),\n"
        "    payload_json String,\n"
        "    error_message Nullable(String)\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (node_kind, node_identity, completed_at, result_id)"
    )


def _object_state_row(record: AdapterObjectStateRecord) -> dict[str, object]:
    observation_id: str = (
        record.observation_id
        or sha256(
            json.dumps(
                {
                    "state_id": record.deployment_id,
                    "state_kind": record.state_kind,
                    "logical_database_name": record.key.database,
                    "logical_object_type": record.key.object_type,
                    "logical_object_name": record.key.name,
                    "physical_database_name": record.physical_database_name,
                    "physical_relation_name": record.physical_relation_name,
                    "object_fingerprint": record.normalized_fingerprint,
                    "canonical_query": record.normalized_query,
                    "observed_at": record.recorded_at,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )
    return {
        "state_id": record.deployment_id,
        "observation_id": observation_id,
        "state_kind": record.state_kind,
        "deployment_id": (
            record.deployment_id
            if record.state_kind == VIRTUAL_OBJECT_STATE_KIND_DEPLOYMENT
            else None
        ),
        "logical_database_name": record.key.database,
        "logical_object_type": record.key.object_type,
        "logical_object_name": record.key.name,
        "physical_database_name": record.physical_database_name,
        "physical_relation_name": record.physical_relation_name,
        "logical_model_database": record.logical_model_database,
        "logical_model_name": record.logical_model_name,
        "is_selected_root": record.is_selected_root,
        "object_fingerprint": record.normalized_fingerprint,
        "canonical_query": record.normalized_query,
        "observed_at": record.recorded_at,
    }


def _deployment_row(record: AdapterDeploymentRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "workflow_fingerprint": record.workflow_fingerprint,
        "replay_lineage_mode": record.replay_lineage_mode,
        "boundary_time": record.boundary_time,
        "created_at": record.created_at,
        "tool_version": record.tool_version,
    }


def _watermark_row(record: AdapterDeploymentWatermarkRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "root_database_name": record.root_key.database,
        "root_object_type": record.root_key.object_type,
        "root_object_name": record.root_key.name,
        "anchor_database_name": record.anchor_key.database,
        "anchor_object_type": record.anchor_key.object_type,
        "anchor_object_name": record.anchor_key.name,
        "boundary_kind": _boundary_kind(record.boundary_key),
        "value_kind": _boundary_value_kind(record.boundary_key),
        "partition_value": _boundary_partition(record.boundary_key),
        "lower_value": record.lower_value,
        "cutoff_value": record.cutoff_value,
        "cutoff_inclusive": record.cutoff_inclusive,
        "captured_at": record.captured_at,
    }


def _publish_event_rows(record: AdapterPublishEventRecord) -> tuple[dict[str, object], ...]:
    binding_identity: tuple[tuple[str, str, str], ...] = tuple(
        (binding.database, binding.logical_name, binding.physical_name)
        for binding in record.bindings
    )
    publication_id: str = sha256(
        json.dumps(
            (record.deployment_id, record.published_at, binding_identity),
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return tuple(
        cast(
            dict[str, object],
            {
                "publication_id": publication_id,
                "deployment_id": record.deployment_id,
                "logical_database_name": binding.database,
                "logical_view_name": binding.logical_name,
                "physical_database_name": binding.database,
                "physical_relation_name": binding.physical_name,
                "published_at": record.published_at,
            },
        )
        for binding in record.bindings
    )


def _publish_rows_for_records(
    records: tuple[AdapterPublishEventRecord, ...],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    record: AdapterPublishEventRecord
    for record in records:
        rows.extend(_publish_event_rows(record))
    return tuple(rows)


def _invocation_row(record: AdapterInvocationRecord) -> dict[str, object]:
    return {
        "invocation_id": record.invocation_id,
        "project_identity": record.project_identity,
        "target_identity": record.target_identity,
        "command": record.command,
        "mode": record.mode,
        "outcome": record.outcome,
        "exit_code": record.exit_code,
        "materialized_outcome": record.materialized_outcome,
        "deployment_id": record.deployment_id,
        "workflow_id": record.workflow_id,
        "selected_node_count": record.selected_node_count,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "duration_ms": record.duration_ms,
        "error_message": record.error_message,
        "summary_json": record.summary_json,
        "tool_version": record.tool_version,
    }


def _node_result_row(record: AdapterNodeResultRecord) -> dict[str, object]:
    return {
        "result_id": record.result_id,
        "invocation_id": record.invocation_id,
        "node_kind": record.node_kind,
        "node_identity": record.node_identity,
        "definition_fingerprint": record.definition_fingerprint,
        "target_identity": record.target_identity,
        "status": record.status,
        "severity": record.severity,
        "failure_count": record.failure_count,
        "completed_at": record.completed_at,
        "payload_json": record.payload_json,
        "error_message": record.error_message,
    }


def _boundary_kind(boundary_key: str) -> str:
    if boundary_key.startswith("_replay_partition="):
        return "offsets"
    return boundary_key.removeprefix("_replay_")


def _boundary_value_kind(boundary_key: str) -> str:
    return (
        REPLAY_VALUE_KIND_INTEGER
        if _boundary_kind(boundary_key)
        in {AdapterReplayBoundaryMode.OFFSETS, AdapterReplayBoundaryMode.CURSOR}
        else REPLAY_VALUE_KIND_TIMESTAMP
    )


def _boundary_partition(boundary_key: str) -> str | None:
    parts: list[str] = boundary_key.split("=", 1)
    return parts[1] if len(parts) == _BOUNDARY_PART_COUNT else None


def render_clickhouse_latest_node_status_query(
    *,
    database: str,
    project_identity: str,
    target_identity: str,
    nodes: tuple[AdapterCurrentQualityNode, ...],
) -> str:
    """Join current manifest fingerprints to latest terminal result history."""

    manifest_sql: str = _manifest_nodes_sql(nodes)
    return (
        f"WITH manifest_nodes AS ({manifest_sql}), latest_results AS ("
        "SELECT result.node_kind AS node_kind, result.node_identity AS node_identity, "
        "argMax(tuple(result.definition_fingerprint, result.status, result.severity, "
        "result.failure_count, result.completed_at, result.payload_json, result.error_message), "
        "tuple(result.completed_at, result.result_id)) AS latest FROM "
        f"{database}.{METADATA_NODE_RESULTS_TABLE_NAME} AS result INNER JOIN "
        f"{database}.{METADATA_INVOCATIONS_TABLE_NAME} AS invocation ON "
        "invocation.invocation_id = result.invocation_id WHERE result.target_identity = "
        f"{_render_sql_literal(target_identity)} AND invocation.project_identity = "
        f"{_render_sql_literal(project_identity)} GROUP BY result.node_kind, "
        "result.node_identity), "
        "matching_results AS (SELECT result.node_kind AS node_kind, "
        "result.node_identity AS node_identity, "
        "argMax(tuple(result.status, result.severity, result.failure_count, result.completed_at, "
        "result.payload_json, result.error_message), tuple(result.completed_at, result.result_id)) "
        f"AS latest FROM {database}.{METADATA_NODE_RESULTS_TABLE_NAME} AS result "
        f"INNER JOIN {database}.{METADATA_INVOCATIONS_TABLE_NAME} AS invocation ON "
        "invocation.invocation_id = result.invocation_id INNER JOIN manifest_nodes AS manifest ON "
        "result.node_kind = manifest.node_kind AND "
        "result.node_identity = manifest.node_identity WHERE "
        f"result.target_identity = {_render_sql_literal(target_identity)} AND "
        f"invocation.project_identity = {_render_sql_literal(project_identity)} AND "
        "result.definition_fingerprint = manifest.definition_fingerprint "
        "GROUP BY result.node_kind, result.node_identity) "
        "SELECT manifest.node_kind AS node_kind, manifest.node_identity AS node_identity, "
        "manifest.definition_fingerprint AS definition_fingerprint, "
        "multiIf(matching.node_identity != '', matching.latest.1, latest.node_identity = '', "
        "'never_run', 'stale') AS current_status, "
        "nullIf(if(matching.node_identity != '', matching.latest.2, latest.latest.3), '') "
        "AS severity, if(matching.node_identity != '', matching.latest.3, latest.latest.4) "
        "AS failure_count, if(matching.node_identity != '', matching.latest.4, latest.latest.5) "
        "AS completed_at, if(matching.node_identity != '', matching.latest.5, latest.latest.6) "
        "AS payload_json, nullIf(if(matching.node_identity != '', matching.latest.6, "
        "latest.latest.7), '') AS error_message FROM manifest_nodes AS manifest "
        "LEFT JOIN latest_results AS latest ON latest.node_kind = manifest.node_kind AND "
        "latest.node_identity = manifest.node_identity LEFT JOIN matching_results AS matching ON "
        "matching.node_kind = manifest.node_kind AND "
        "matching.node_identity = manifest.node_identity "
        "ORDER BY manifest.node_kind, manifest.node_identity"
    )


def _manifest_nodes_sql(nodes: tuple[AdapterCurrentQualityNode, ...]) -> str:
    if not nodes:
        return (
            "SELECT CAST('' AS String) AS node_kind, CAST('' AS String) AS node_identity, "
            "CAST('' AS String) AS definition_fingerprint WHERE false"
        )
    rows: str = ", ".join(
        f"({_render_sql_literal(node.node_kind)}, {_render_sql_literal(node.node_identity)}, "
        f"{_render_sql_literal(node.definition_fingerprint)})"
        for node in nodes
    )
    return (
        "SELECT * FROM VALUES('node_kind String, node_identity String, "
        f"definition_fingerprint String', {rows})"
    )


def load_clickhouse_target_ownership(
    *, connection: AdapterConnection, database: str
) -> tuple[AdapterOwnershipRecord, ...]:
    """Return every ownership record recorded for one ClickHouse database."""

    if not _direct_target_events_table_exists(connection=connection, database=database):
        return ()
    event_result: AdapterQueryResult = connection.query(
        "SELECT database_name, relation_name, current_state.2 AS event_kind, "
        "current_state.3 AS resource_kind, current_state.4 AS logical_model_database, "
        "current_state.5 AS logical_model_name, current_state.6 AS tool_version, "
        "current_state.7 AS replay_set_id FROM (SELECT database_name, relation_name, "
        "argMax(tuple(event_id, event_kind, resource_kind, logical_model_database, "
        "logical_model_name, tool_version, replay_set_id), tuple(recorded_at, event_id)) "
        f"AS current_state FROM {database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} "
        "GROUP BY database_name, relation_name) WHERE current_state.2 != 'released' "
        "ORDER BY database_name, relation_name"
    )
    replay_set_ids: tuple[str, ...] = tuple(
        sorted({str(row[7]) for row in event_result.rows if row[7] is not None})
    )
    coverage_by_replay_set: dict[str, tuple[AdapterReplayCoverageRange, ...]] = (
        _load_direct_replay_ranges(
            connection=connection,
            database=database,
            replay_set_ids=replay_set_ids,
        )
    )
    return tuple(
        _ownership_record(row=row, coverage_by_replay_set=coverage_by_replay_set)
        for row in event_result.rows
    )


def render_clickhouse_target_ownership(
    *, database: str, records: tuple[AdapterOwnershipRecord, ...]
) -> tuple[str, ...]:
    """Render deterministic ownership claims as one executable ClickHouse insert."""

    if not records:
        return ()
    replay_set_id_by_model: dict[tuple[str, str | None, str], str] = {
        (record.database_name, record.logical_model_database, record.logical_model_name): (
            _direct_replay_set_id(record)
        )
        for record in records
    }
    range_rows: tuple[str, ...] = _direct_replay_range_values(
        records=records,
        replay_set_id_by_model=replay_set_id_by_model,
    )
    workflow_id: str = _direct_ownership_workflow_id(records=records)
    event_rows: str = ",\n".join(
        _render_direct_target_event_values(
            record=record,
            workflow_id=workflow_id,
            replay_set_id=replay_set_id_by_model[
                (record.database_name, record.logical_model_database, record.logical_model_name)
            ],
        )
        for record in records
    )
    statements: list[str] = []
    if range_rows:
        joined_range_rows: str = ",\n".join(range_rows)
        statements.append(
            f"INSERT INTO {database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
            "(replay_set_id, target_database_name, logical_model_database, logical_model_name, "
            "range_present, driving_input_relation_name, replay_boundary_mode, partition_value, "
            "source_partition_column_name, source_position_column_name, "
            "source_timestamp_column_name, lower_value, upper_value, replay_cutoff_value, "
            "captured_at) VALUES\n"
            f"{joined_range_rows};"
        )
    statements.append(
        f"INSERT INTO {database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} "
        "(event_id, workflow_id, event_kind, database_name, relation_name, resource_kind, "
        "logical_model_database, logical_model_name, tool_version, replay_set_id, recorded_at) "
        f"VALUES\n{event_rows};"
    )
    return tuple(statements)


def render_clickhouse_target_ownership_removal(
    *, database: str, target_database: str, relation_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Render append-only release events for retired ownership claims."""

    if not relation_names:
        return ()
    quoted_names: str = ", ".join(_render_sql_literal(name) for name in relation_names)
    quoted_target_database: str = _render_sql_literal(target_database)
    workflow_id: str = sha256(
        f"release:{target_database}:{','.join(sorted(relation_names))}".encode()
    ).hexdigest()
    return (
        f"INSERT INTO {database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} "
        "(event_id, workflow_id, event_kind, database_name, relation_name, resource_kind, "
        "logical_model_database, logical_model_name, tool_version, replay_set_id, recorded_at) "
        "SELECT hex(SHA256(concat('release:', current_state.1))), "
        f"'{workflow_id}', 'released', database_name, relation_name, current_state.3, "
        "current_state.4, current_state.5, current_state.6, NULL, now64(3, 'UTC') FROM ("
        "SELECT database_name, relation_name, argMax(tuple(event_id, event_kind, resource_kind, "
        "logical_model_database, logical_model_name, tool_version), "
        "tuple(recorded_at, event_id)) AS current_state "
        f"FROM {database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} "
        f"WHERE database_name = {quoted_target_database} AND relation_name IN ({quoted_names}) "
        "GROUP BY database_name, relation_name) WHERE current_state.2 != 'released';",
    )


def _render_direct_target_event_values(
    *, record: AdapterOwnershipRecord, workflow_id: str, replay_set_id: str | None
) -> str:
    event_id: str = sha256(
        f"{workflow_id}:{record.database_name}:{record.relation_name}:claimed".encode()
    ).hexdigest()
    values: tuple[object, ...] = (
        event_id,
        workflow_id,
        "claimed",
        record.database_name,
        record.relation_name,
        record.resource_kind,
        record.logical_model_database,
        record.logical_model_name,
        record.tool_version,
        replay_set_id,
    )
    rendered_values: str = ", ".join(_render_sql_literal(value) for value in values)
    return f"({rendered_values}, now64(3, 'UTC'))"


def _render_insert_statement(statement: ClickHouseMetadataStatement) -> str:
    rendered_rows: list[str] = []
    row: dict[str, object]
    for row in statement.rows:
        rendered_values: tuple[str, ...] = tuple(
            _render_sql_literal(value) for value in row.values()
        )
        rendered_rows.append(f"({', '.join(rendered_values)})")
    joined_rows: str = ",\n".join(rendered_rows)
    return f"{statement.sql}\n{joined_rows};"


def _render_sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        escaped_value: str = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped_value}'"
    raise AdapterResultError(f"Cannot render ClickHouse SQL literal for {type(value).__name__}")


def _terminate_sql(statement: str) -> str:
    return f"{statement.rstrip().rstrip(';')};"


def _direct_target_events_table_exists(*, connection: AdapterConnection, database: str) -> bool:
    result: AdapterQueryResult = connection.query(
        OWNERSHIP_TABLE_EXISTS_QUERY.format(
            database=database, table=METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME
        )
    )
    return bool(result.rows)


def _ownership_record(
    *,
    row: tuple[object, ...],
    coverage_by_replay_set: dict[str, tuple[AdapterReplayCoverageRange, ...]],
) -> AdapterOwnershipRecord:
    if len(row) != OWNERSHIP_EVENT_ROW_LENGTH:
        raise AdapterResultError(
            f"ClickHouse ownership row had {len(row)} columns where "
            f"{OWNERSHIP_EVENT_ROW_LENGTH} were required"
        )
    replay_set_id: str | None = _optional_text(row[7])
    return AdapterOwnershipRecord(
        database_name=str(row[0]),
        relation_name=str(row[1]),
        resource_kind=str(row[3]),
        logical_model_database=_optional_text(row[4]),
        logical_model_name=str(row[5]),
        owning_mode="direct",
        tool_version=str(row[6]),
        replay_coverage=(
            () if replay_set_id is None else coverage_by_replay_set.get(replay_set_id, ())
        ),
    )


def _load_direct_replay_ranges(
    *,
    connection: AdapterConnection,
    database: str,
    replay_set_ids: tuple[str, ...],
) -> dict[str, tuple[AdapterReplayCoverageRange, ...]]:
    if not replay_set_ids:
        return {}
    quoted_ids: str = ", ".join(_render_sql_literal(value) for value in replay_set_ids)
    result: AdapterQueryResult = connection.query(
        "SELECT DISTINCT replay_set_id, range_present, driving_input_relation_name, "
        "replay_boundary_mode, "
        "partition_value, source_partition_column_name, source_position_column_name, "
        "source_timestamp_column_name, lower_value, upper_value, replay_cutoff_value "
        f"FROM {database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        f"WHERE replay_set_id IN ({quoted_ids}) ORDER BY replay_set_id, replay_boundary_mode, "
        "partition_value, lower_value, upper_value"
    )
    grouped: dict[str, list[AdapterReplayCoverageRange]] = {}
    row: tuple[object, ...]
    for row in result.rows:
        if len(row) != OWNERSHIP_RANGE_ROW_LENGTH:
            raise AdapterResultError(
                f"ClickHouse replay range row had {len(row)} columns where "
                f"{OWNERSHIP_RANGE_ROW_LENGTH} were required"
            )
        replay_set_id: str = str(row[0])
        if not bool(row[1]):
            grouped.setdefault(replay_set_id, [])
            continue
        mode: str = str(row[3])
        grouped.setdefault(replay_set_id, []).append(
            AdapterReplayCoverageRange(
                driving_input_relation_name=str(row[2]),
                replay_boundary_mode=mode,
                boundary_key=_direct_boundary_key(
                    mode=mode, partition_value=_optional_text(row[4])
                ),
                source_partition_column_name=_optional_text(row[5]),
                source_position_column_name=str(row[6]),
                source_timestamp_column_name=_optional_text(row[7]),
                lower_value=str(row[8]),
                upper_value=str(row[9]),
            )
        )
    return {key: tuple(value) for key, value in grouped.items()}


def _direct_replay_set_id(record: AdapterOwnershipRecord) -> str:
    payload: dict[str, object] = {
        "database_name": record.database_name,
        "logical_model_database": record.logical_model_database,
        "logical_model_name": record.logical_model_name,
        "ranges": [_replay_coverage_payload(value) for value in record.replay_coverage],
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _direct_ownership_workflow_id(*, records: tuple[AdapterOwnershipRecord, ...]) -> str:
    payload: list[dict[str, object]] = [
        {
            "database_name": record.database_name,
            "relation_name": record.relation_name,
            "resource_kind": record.resource_kind,
            "logical_model_database": record.logical_model_database,
            "logical_model_name": record.logical_model_name,
            "tool_version": record.tool_version,
            "replay_set_id": _direct_replay_set_id(record),
        }
        for record in records
    ]
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _direct_replay_range_values(
    *,
    records: tuple[AdapterOwnershipRecord, ...],
    replay_set_id_by_model: dict[tuple[str, str | None, str], str],
) -> tuple[str, ...]:
    rendered: list[str] = []
    seen_replay_sets: set[str] = set()
    record: AdapterOwnershipRecord
    for record in records:
        replay_set_id: str = replay_set_id_by_model[
            (record.database_name, record.logical_model_database, record.logical_model_name)
        ]
        if replay_set_id in seen_replay_sets:
            continue
        seen_replay_sets.add(replay_set_id)
        coverage_rows: tuple[AdapterReplayCoverageRange | None, ...] = (
            tuple(record.replay_coverage) if record.replay_coverage else (None,)
        )
        coverage: AdapterReplayCoverageRange | None
        for coverage in coverage_rows:
            values: tuple[object, ...] = (
                replay_set_id,
                record.database_name,
                record.logical_model_database,
                record.logical_model_name,
                coverage is not None,
                None if coverage is None else coverage.driving_input_relation_name,
                None if coverage is None else str(coverage.replay_boundary_mode),
                None if coverage is None else _direct_partition_value(coverage),
                None if coverage is None else coverage.source_partition_column_name,
                None if coverage is None else coverage.source_position_column_name,
                None if coverage is None else coverage.source_timestamp_column_name,
                None if coverage is None else coverage.lower_value,
                None if coverage is None else coverage.upper_value,
                None if coverage is None else coverage.upper_value,
            )
            literals: str = ", ".join(_render_sql_literal(value) for value in values)
            rendered.append(f"({literals}, now64(3, 'UTC'))")
    return tuple(rendered)


def _replay_coverage_payload(coverage: AdapterReplayCoverageRange) -> dict[str, str]:
    return {
        "driving_input_relation_name": coverage.driving_input_relation_name,
        "replay_boundary_mode": str(coverage.replay_boundary_mode),
        "boundary_key": coverage.boundary_key,
        "source_partition_column_name": coverage.source_partition_column_name or "",
        "source_position_column_name": coverage.source_position_column_name,
        "source_timestamp_column_name": coverage.source_timestamp_column_name or "",
        "lower_value": coverage.lower_value,
        "upper_value": coverage.upper_value,
    }


def _direct_partition_value(coverage: AdapterReplayCoverageRange) -> str | None:
    if coverage.replay_boundary_mode != AdapterReplayBoundaryMode.OFFSETS:
        return None
    boundary_parts: tuple[str, ...] = tuple(coverage.boundary_key.split("=", 1))
    if len(boundary_parts) != _BOUNDARY_PART_COUNT or not boundary_parts[1]:
        raise AdapterResultError(
            f"Offset replay boundary '{coverage.boundary_key}' has no partition value"
        )
    return boundary_parts[1]


def _direct_boundary_key(*, mode: str, partition_value: str | None) -> str:
    replay_mode: AdapterReplayBoundaryMode = AdapterReplayBoundaryMode(mode)
    if replay_mode == AdapterReplayBoundaryMode.OFFSETS:
        if partition_value is None:
            raise AdapterResultError("Offset replay range has no partition value")
        return f"_replay_partition={partition_value}"
    return {
        AdapterReplayBoundaryMode.TIMESTAMP: "_replay_timestamp",
        AdapterReplayBoundaryMode.LANDED_AT: "_replay_landed_at",
        AdapterReplayBoundaryMode.CURSOR: "_replay_cursor",
    }[replay_mode]


def _optional_text(value: object) -> str | None:
    if value in EMPTY_DEFAULT_EXPRESSIONS:
        return None
    return str(value)
