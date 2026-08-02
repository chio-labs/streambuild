"""Migrate and persist StreamBuild metadata in ClickHouse."""

import json
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME,
    METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_OBJECT_STATE_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
    METADATA_SCHEMA_VERSIONS_TABLE_NAME,
    METADATA_TARGET_OWNERSHIP_TABLE_NAME,
)
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterDeploymentRecord,
    AdapterDeploymentRuntimeDetailRecord,
    AdapterDeploymentWatermarkRecord,
    AdapterMetadataObjectKey,
    AdapterMetadataState,
    AdapterObjectStateRecord,
    AdapterOwnershipRecord,
    AdapterPreparedObjectMapping,
    AdapterPublishEventRecord,
    AdapterQueryResult,
    AdapterReplayCoverageRange,
)
from streambuild.adapters.clickhouse.constants import (
    EMPTY_DEFAULT_EXPRESSIONS,
    OWNERSHIP_ROW_LENGTH,
    OWNERSHIP_TABLE_EXISTS_QUERY,
)
from streambuild.adapters.clickhouse.models import ClickHouseMetadataStatement

_CURRENT_STATE_SCHEMA_VERSION: int = 1


def render_clickhouse_metadata_migration_statements(database: str) -> tuple[str, ...]:
    """Render the current additive ClickHouse metadata migration."""

    return (
        _render_object_state_table(database),
        _render_deployments_table(database),
        _render_deployment_watermarks_table(database),
        _render_deployment_runtime_details_table(database),
        _render_publish_history_table(database),
        _render_target_ownership_table(database),
        (
            f"ALTER TABLE {database}.{METADATA_DEPLOYMENTS_TABLE_NAME} "
            "ADD COLUMN IF NOT EXISTS replay_lineage_mode String DEFAULT 'offsets' AFTER status"
        ),
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
                "(deployment_id, database_name, object_type, object_name, normalized_fingerprint, "
                "normalized_query, recorded_at) VALUES"
            ),
            rows=tuple(_object_state_row(record) for record in state.object_states),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_DEPLOYMENTS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_DEPLOYMENTS_TABLE_NAME} "
                "(deployment_id, created_at, status, replay_lineage_mode, "
                "selected_root_keys_json, warning_codes_json, prepared_object_mappings_json) VALUES"
            ),
            rows=tuple(_deployment_row(record) for record in state.deployments),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} "
                "(deployment_id, root_database_name, root_object_type, root_object_name, "
                "anchor_database_name, anchor_object_type, anchor_object_name, boundary_key, "
                "cutoff_value) VALUES"
            ),
            rows=tuple(_watermark_row(record) for record in state.deployment_watermarks),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME} "
                "(deployment_id, root_database_name, root_object_type, root_object_name, "
                "state_kind, replay_strategy, active_deployment_id, anchor_database_name, "
                "anchor_object_type, anchor_object_name, anchor_physical_name, execution_mode, "
                "configured_backfill_mode, execution_lookback_seconds, "
                "live_target_names_json) VALUES"
            ),
            rows=tuple(_runtime_detail_row(record) for record in state.deployment_runtime_details),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME} "
                "(deployment_id, published_at, logical_view_names_json) VALUES"
            ),
            rows=tuple(_publish_event_row(record) for record in state.publish_events),
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
        ") ENGINE = ReplacingMergeTree(applied_at)\n"
        "ORDER BY (version)"
    )


def _render_object_state_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_OBJECT_STATE_TABLE_NAME} (\n"
        "    deployment_id String,\n"
        "    database_name Nullable(String),\n"
        "    object_type String,\n"
        "    object_name String,\n"
        "    normalized_fingerprint String,\n"
        "    normalized_query Nullable(String),\n"
        "    recorded_at DateTime64(3, 'UTC')\n"
        ") ENGINE = ReplacingMergeTree(recorded_at)\n"
        "ORDER BY (deployment_id, object_type, object_name)"
    )


def _render_deployments_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_DEPLOYMENTS_TABLE_NAME} (\n"
        "    deployment_id String,\n"
        "    created_at DateTime64(3, 'UTC'),\n"
        "    status String,\n"
        "    replay_lineage_mode String,\n"
        "    selected_root_keys_json String,\n"
        "    warning_codes_json String,\n"
        "    prepared_object_mappings_json String\n"
        ") ENGINE = ReplacingMergeTree(created_at)\n"
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
        "    boundary_key String,\n"
        "    cutoff_value String\n"
        ") ENGINE = ReplacingMergeTree()\n"
        "ORDER BY (deployment_id, root_object_type, root_object_name, boundary_key)"
    )


def _render_deployment_runtime_details_table(database: str) -> str:
    return (
        "CREATE TABLE IF NOT EXISTS "
        f"{database}.{METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME} (\n"
        "    deployment_id String,\n"
        "    root_database_name Nullable(String),\n"
        "    root_object_type String,\n"
        "    root_object_name String,\n"
        "    state_kind String,\n"
        "    replay_strategy String,\n"
        "    active_deployment_id Nullable(String),\n"
        "    anchor_database_name Nullable(String),\n"
        "    anchor_object_type String,\n"
        "    anchor_object_name String,\n"
        "    anchor_physical_name Nullable(String),\n"
        "    execution_mode Nullable(String),\n"
        "    configured_backfill_mode Nullable(String),\n"
        "    execution_lookback_seconds Nullable(Int64),\n"
        "    live_target_names_json String\n"
        ") ENGINE = ReplacingMergeTree()\n"
        "ORDER BY (deployment_id, root_object_type, root_object_name)"
    )


def _render_publish_history_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME} (\n"
        "    deployment_id String,\n"
        "    published_at DateTime64(3, 'UTC'),\n"
        "    logical_view_names_json String\n"
        ") ENGINE = ReplacingMergeTree(published_at)\n"
        "ORDER BY (deployment_id, published_at)"
    )


def _render_target_ownership_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} (\n"
        "    database_name String,\n"
        "    relation_name String,\n"
        "    resource_kind String,\n"
        "    logical_model_database Nullable(String),\n"
        "    logical_model_name String,\n"
        "    owning_mode String,\n"
        "    tool_version String,\n"
        "    replay_coverage_json String DEFAULT '[]',\n"
        "    created_at DateTime64(3, 'UTC'),\n"
        "    updated_at DateTime64(3, 'UTC')\n"
        ") ENGINE = ReplacingMergeTree(updated_at)\n"
        "ORDER BY (database_name, relation_name)"
    )


def _object_state_row(record: AdapterObjectStateRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "database_name": record.key.database,
        "object_type": record.key.object_type,
        "object_name": record.key.name,
        "normalized_fingerprint": record.normalized_fingerprint,
        "normalized_query": record.normalized_query,
        "recorded_at": record.recorded_at,
    }


def _deployment_row(record: AdapterDeploymentRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "created_at": record.created_at,
        "status": record.status,
        "replay_lineage_mode": record.replay_lineage_mode,
        "selected_root_keys_json": json.dumps(
            [_object_key_payload(key) for key in record.selected_root_keys]
        ),
        "warning_codes_json": json.dumps(list(record.warning_codes)),
        "prepared_object_mappings_json": json.dumps(
            [_prepared_mapping_payload(mapping) for mapping in record.prepared_object_mappings]
        ),
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
        "boundary_key": record.boundary_key,
        "cutoff_value": record.cutoff_value,
    }


def _runtime_detail_row(record: AdapterDeploymentRuntimeDetailRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "root_database_name": record.root_key.database,
        "root_object_type": record.root_key.object_type,
        "root_object_name": record.root_key.name,
        "state_kind": record.state_kind,
        "replay_strategy": record.replay_strategy,
        "active_deployment_id": record.active_deployment_id,
        "anchor_database_name": record.anchor_key.database,
        "anchor_object_type": record.anchor_key.object_type,
        "anchor_object_name": record.anchor_key.name,
        "anchor_physical_name": record.anchor_physical_name,
        "execution_mode": record.execution_mode,
        "configured_backfill_mode": record.configured_backfill_mode,
        "execution_lookback_seconds": record.execution_lookback_seconds,
        "live_target_names_json": json.dumps(list(record.live_target_names)),
    }


def _publish_event_row(record: AdapterPublishEventRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "published_at": record.published_at,
        "logical_view_names_json": json.dumps(list(record.logical_view_names)),
    }


def _object_key_payload(key: AdapterMetadataObjectKey) -> dict[str, object]:
    return {"database": key.database, "object_type": key.object_type, "name": key.name}


def _prepared_mapping_payload(mapping: AdapterPreparedObjectMapping) -> dict[str, object]:
    return {
        "logical_key": _object_key_payload(mapping.logical_key),
        "physical_name": mapping.physical_name,
        "logical_model_name": mapping.logical_model_name,
    }


def load_clickhouse_target_ownership(
    *, connection: AdapterConnection, database: str
) -> tuple[AdapterOwnershipRecord, ...]:
    """Return every ownership record recorded for one ClickHouse database."""

    if not _ownership_table_exists(connection=connection, database=database):
        return ()
    result: AdapterQueryResult = connection.query(
        "SELECT database_name, relation_name, resource_kind, logical_model_database, "
        "logical_model_name, owning_mode, tool_version, replay_coverage_json "
        f"FROM {database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} FINAL "
        "ORDER BY database_name, relation_name"
    )
    return tuple(_ownership_record(row=row) for row in result.rows)


def render_clickhouse_target_ownership(
    *, database: str, records: tuple[AdapterOwnershipRecord, ...]
) -> tuple[str, ...]:
    """Render deterministic ownership claims as one executable ClickHouse insert."""

    if not records:
        return ()
    rendered_rows: str = ",\n".join(_render_ownership_values(record) for record in records)
    return (
        f"INSERT INTO {database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} "
        "(database_name, relation_name, resource_kind, logical_model_database, "
        "logical_model_name, owning_mode, tool_version, replay_coverage_json, created_at, "
        f"updated_at) VALUES\n{rendered_rows};",
    )


def render_clickhouse_target_ownership_removal(
    *, database: str, target_database: str, relation_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Render exact synchronous removal SQL for retired ownership claims."""

    if not relation_names:
        return ()
    quoted_names: str = ", ".join(_render_sql_literal(name) for name in relation_names)
    quoted_target_database: str = _render_sql_literal(target_database)
    return (
        f"ALTER TABLE {database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} "
        f"DELETE WHERE database_name = {quoted_target_database} "
        f"AND relation_name IN ({quoted_names}) SETTINGS mutations_sync = 2;",
    )


def _render_ownership_values(record: AdapterOwnershipRecord) -> str:
    replay_coverage_json: str = json.dumps(
        [_replay_coverage_payload(coverage) for coverage in record.replay_coverage]
    )
    values: tuple[object, ...] = (
        record.database_name,
        record.relation_name,
        record.resource_kind,
        record.logical_model_database,
        record.logical_model_name,
        str(record.owning_mode),
        record.tool_version,
        replay_coverage_json,
    )
    rendered_values: str = ", ".join(_render_sql_literal(value) for value in values)
    return f"({rendered_values}, now64(3, 'UTC'), now64(3, 'UTC'))"


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


def _ownership_table_exists(*, connection: AdapterConnection, database: str) -> bool:
    result: AdapterQueryResult = connection.query(
        OWNERSHIP_TABLE_EXISTS_QUERY.format(
            database=database, table=METADATA_TARGET_OWNERSHIP_TABLE_NAME
        )
    )
    return bool(result.rows)


def _ownership_record(*, row: tuple[object, ...]) -> AdapterOwnershipRecord:
    if len(row) != OWNERSHIP_ROW_LENGTH:
        raise AdapterResultError(
            f"ClickHouse ownership row had {len(row)} columns where "
            f"{OWNERSHIP_ROW_LENGTH} were required"
        )
    return AdapterOwnershipRecord(
        database_name=str(row[0]),
        relation_name=str(row[1]),
        resource_kind=str(row[2]),
        logical_model_database=_optional_text(row[3]),
        logical_model_name=str(row[4]),
        owning_mode=str(row[5]),
        tool_version=str(row[6]),
        replay_coverage=_replay_coverage_ranges(row[7]),
    )


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


def _replay_coverage_ranges(value: object) -> tuple[AdapterReplayCoverageRange, ...]:
    payloads: list[dict[str, object]] = cast(list[dict[str, object]], json.loads(str(value)))
    return tuple(
        AdapterReplayCoverageRange(
            driving_input_relation_name=str(payload["driving_input_relation_name"]),
            replay_boundary_mode=str(payload["replay_boundary_mode"]),
            boundary_key=str(payload["boundary_key"]),
            source_partition_column_name=(str(payload["source_partition_column_name"]) or None),
            source_position_column_name=str(payload["source_position_column_name"]),
            source_timestamp_column_name=(str(payload["source_timestamp_column_name"]) or None),
            lower_value=str(payload["lower_value"]),
            upper_value=str(payload["upper_value"]),
        )
        for payload in payloads
    )


def _optional_text(value: object) -> str | None:
    if value in EMPTY_DEFAULT_EXPRESSIONS:
        return None
    return str(value)
