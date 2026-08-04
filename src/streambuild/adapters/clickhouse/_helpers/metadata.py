"""Migrate and persist StreamBuild metadata in ClickHouse."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import cast

from streambuild.adapter.constants import (
    METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_DIRECT_FINGERPRINTS_TABLE_NAME,
    METADATA_DIRECT_REPLAY_CHECKPOINTS_TABLE_NAME,
    METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME,
    METADATA_INVOCATIONS_TABLE_NAME,
    METADATA_NODE_RESULTS_TABLE_NAME,
    METADATA_OBJECT_STATE_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
    METADATA_RUN_EVENTS_TABLE_NAME,
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
    AdapterPublishEventRecord,
    AdapterRunEventRecord,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
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
        _render_direct_replay_checkpoints_table(database),
        _render_direct_fingerprints_table(database),
        _render_invocations_table(database),
        _render_node_results_table(database),
        _render_run_events_table(database),
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
        "    capture_id String,\n"
        "    replay_set_id String,\n"
        "    workflow_id String,\n"
        "    checkpoint_sequence UInt8,\n"
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
        "    captured_at DateTime64(9, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (capture_id, replay_set_id, range_present)"
    )


def _render_direct_replay_checkpoints_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_DIRECT_REPLAY_CHECKPOINTS_TABLE_NAME} (\n"
        "    checkpoint_id String,\n"
        "    workflow_id String,\n"
        "    target_database_name String,\n"
        "    logical_model_name String,\n"
        "    capture_id String,\n"
        "    replay_set_id String,\n"
        "    checkpoint_sequence UInt8,\n"
        "    recorded_at DateTime64(9, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (checkpoint_id, checkpoint_sequence, recorded_at, capture_id)"
    )


def _render_direct_fingerprints_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_DIRECT_FINGERPRINTS_TABLE_NAME} (\n"
        "    fingerprint_id String, logical_model_identity String, physical_database String,\n"
        "    physical_relation String, resource_kind String, definition_sql String,\n"
        "    definition_hash String, rendered_definition_hash String,\n"
        "    schema_fingerprint String, workflow_id String, tool_version String,\n"
        "    succeeded_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree ORDER BY (logical_model_identity, succeeded_at, fingerprint_id)"
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


def _render_run_events_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_RUN_EVENTS_TABLE_NAME} (\n"
        "    invocation_id String,\n"
        "    sequence UInt64,\n"
        "    emitted_at DateTime64(3, 'UTC'),\n"
        "    event_kind LowCardinality(String),\n"
        "    step_id Nullable(String),\n"
        "    phase Nullable(String),\n"
        "    payload_json String\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (invocation_id, sequence)"
    )


def render_clickhouse_run_event_inserts(
    *,
    database: str,
    events: tuple[AdapterRunEventRecord, ...],
    include_migration: bool = False,
) -> tuple[str, ...]:
    """Render incremental run-event inserts, optionally preceded by the migration."""

    if not events:
        return ()
    statement: ClickHouseMetadataStatement = ClickHouseMetadataStatement(
        table=f"{database}.{METADATA_RUN_EVENTS_TABLE_NAME}",
        sql=(
            f"INSERT INTO {database}.{METADATA_RUN_EVENTS_TABLE_NAME} "
            "(invocation_id, sequence, emitted_at, event_kind, step_id, phase, "
            "payload_json) VALUES"
        ),
        rows=tuple(_run_event_row(record) for record in events),
    )
    inserts: tuple[str, ...] = (_render_insert_statement(statement),)
    if not include_migration:
        return inserts
    return (*render_clickhouse_metadata_migration_workflow(database), *inserts)


def _run_event_row(record: AdapterRunEventRecord) -> dict[str, object]:
    return {
        "invocation_id": record.invocation_id,
        "sequence": record.sequence,
        "emitted_at": record.emitted_at,
        "event_kind": record.event_kind,
        "step_id": record.step_id,
        "phase": record.phase,
        "payload_json": record.payload_json,
    }


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
