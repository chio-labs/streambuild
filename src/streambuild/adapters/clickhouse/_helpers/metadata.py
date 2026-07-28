"""Migrate and persist StreamBuild metadata in ClickHouse."""

import json
from datetime import UTC, datetime

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
from streambuild.adapter.exceptions import AdapterResultError, AdapterWarehouseError
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
)
from streambuild.adapters.clickhouse.constants import (
    EMPTY_DEFAULT_EXPRESSIONS,
    OWNERSHIP_ROW_LENGTH,
    OWNERSHIP_TABLE_EXISTS_QUERY,
)
from streambuild.adapters.clickhouse.models import ClickHouseMetadataStatement

_CURRENT_STATE_SCHEMA_VERSION: int = 1
_REQUIRED_SCHEMA_COLUMNS: tuple[tuple[str, str], ...] = (
    (METADATA_OBJECT_STATE_TABLE_NAME, "deployment_id"),
    (METADATA_OBJECT_STATE_TABLE_NAME, "database_name"),
    (METADATA_OBJECT_STATE_TABLE_NAME, "object_type"),
    (METADATA_OBJECT_STATE_TABLE_NAME, "object_name"),
    (METADATA_OBJECT_STATE_TABLE_NAME, "normalized_fingerprint"),
    (METADATA_OBJECT_STATE_TABLE_NAME, "normalized_query"),
    (METADATA_OBJECT_STATE_TABLE_NAME, "recorded_at"),
    (METADATA_DEPLOYMENTS_TABLE_NAME, "deployment_id"),
    (METADATA_DEPLOYMENTS_TABLE_NAME, "created_at"),
    (METADATA_DEPLOYMENTS_TABLE_NAME, "status"),
    (METADATA_DEPLOYMENTS_TABLE_NAME, "replay_lineage_mode"),
    (METADATA_DEPLOYMENTS_TABLE_NAME, "selected_root_keys_json"),
    (METADATA_DEPLOYMENTS_TABLE_NAME, "warning_codes_json"),
    (METADATA_DEPLOYMENTS_TABLE_NAME, "prepared_object_mappings_json"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "deployment_id"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "root_database_name"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "root_object_type"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "root_object_name"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "anchor_database_name"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "anchor_object_type"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "anchor_object_name"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "boundary_key"),
    (METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME, "cutoff_value"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "deployment_id"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "root_database_name"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "root_object_type"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "root_object_name"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "state_kind"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "replay_strategy"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "active_deployment_id"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "anchor_database_name"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "anchor_object_type"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "anchor_object_name"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "anchor_physical_name"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "execution_mode"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "configured_backfill_mode"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "execution_lookback_seconds"),
    (METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME, "live_target_names_json"),
    (METADATA_PUBLISH_HISTORY_TABLE_NAME, "deployment_id"),
    (METADATA_PUBLISH_HISTORY_TABLE_NAME, "published_at"),
    (METADATA_PUBLISH_HISTORY_TABLE_NAME, "logical_view_names_json"),
    (METADATA_SCHEMA_VERSIONS_TABLE_NAME, "version"),
    (METADATA_SCHEMA_VERSIONS_TABLE_NAME, "applied_at"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "database_name"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "relation_name"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "resource_kind"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "logical_model_database"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "logical_model_name"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "owning_mode"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "tool_version"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "created_at"),
    (METADATA_TARGET_OWNERSHIP_TABLE_NAME, "updated_at"),
)


def migrate_clickhouse_metadata_state(*, connection: AdapterConnection, database: str) -> None:
    """Apply pending additive ClickHouse metadata migrations."""

    connection.ensure_database(database)
    connection.command(_render_schema_versions_table(database))
    if _CURRENT_STATE_SCHEMA_VERSION in _load_applied_versions(
        connection=connection, database=database
    ):
        return
    statement: str
    for statement in render_clickhouse_metadata_migration_statements(database):
        connection.command(statement)
    _validate_schema_postconditions(connection=connection, database=database)
    connection.insert_rows(
        table=f"{database}.{METADATA_SCHEMA_VERSIONS_TABLE_NAME}",
        rows=(
            {
                "version": _CURRENT_STATE_SCHEMA_VERSION,
                "applied_at": datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            },
        ),
    )


def persist_clickhouse_metadata_state(
    *,
    connection: AdapterConnection,
    database: str,
    state: AdapterMetadataState,
) -> None:
    """Persist adapter-neutral metadata records in ClickHouse."""

    statement: ClickHouseMetadataStatement
    for statement in build_clickhouse_metadata_insert_statements(database=database, state=state):
        if statement.rows:
            connection.insert_rows(table=statement.table, rows=statement.rows)


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


def _load_applied_versions(*, connection: AdapterConnection, database: str) -> frozenset[int]:
    result: AdapterQueryResult = connection.query(
        f"SELECT DISTINCT version FROM {database}.{METADATA_SCHEMA_VERSIONS_TABLE_NAME}"
    )
    return frozenset(int(str(row[0])) for row in result.rows)


def _validate_schema_postconditions(*, connection: AdapterConnection, database: str) -> None:
    required_table_names: set[str] = set()
    required_table: str
    required_column: str
    for required_table, required_column in _REQUIRED_SCHEMA_COLUMNS:
        del required_column
        required_table_names.add(required_table)
    table_names: str = ", ".join(f"'{table_name}'" for table_name in sorted(required_table_names))
    result: AdapterQueryResult = connection.query(
        "SELECT table, name FROM system.columns "
        f"WHERE database = '{database}' AND table IN ({table_names})"
    )
    observed_columns: frozenset[tuple[str, str]] = frozenset(
        (str(row[0]), str(row[1])) for row in result.rows
    )
    missing_columns: tuple[tuple[str, str], ...] = tuple(
        required for required in _REQUIRED_SCHEMA_COLUMNS if required not in observed_columns
    )
    if missing_columns:
        raise AdapterWarehouseError(
            f"ClickHouse metadata migration {_CURRENT_STATE_SCHEMA_VERSION} "
            f"did not establish required columns: {missing_columns!r}"
        )


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
    }


def load_clickhouse_target_ownership(
    *, connection: AdapterConnection, database: str
) -> tuple[AdapterOwnershipRecord, ...]:
    """Return every ownership record recorded for one ClickHouse database."""

    if not _ownership_table_exists(connection=connection, database=database):
        return ()
    result: AdapterQueryResult = connection.query(
        "SELECT database_name, relation_name, resource_kind, logical_model_database, "
        "logical_model_name, owning_mode, tool_version "
        f"FROM {database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} FINAL "
        "ORDER BY database_name, relation_name"
    )
    return tuple(_ownership_record(row=row) for row in result.rows)


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
    )


def _optional_text(value: object) -> str | None:
    if value in EMPTY_DEFAULT_EXPRESSIONS:
        return None
    return str(value)
