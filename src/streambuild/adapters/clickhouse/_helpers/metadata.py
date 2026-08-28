"""Migrate and persist StreamBuild metadata in ClickHouse."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_DIRECT_FINGERPRINTS_TABLE_NAME,
    METADATA_INVOCATIONS_TABLE_NAME,
    METADATA_MANIFESTS_TABLE_NAME,
    METADATA_NODE_RESULTS_TABLE_NAME,
    METADATA_OBJECT_STATE_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
    METADATA_RUN_EVENTS_TABLE_NAME,
    METADATA_RUN_STATEMENTS_TABLE_NAME,
    METADATA_SCHEMA_VERSIONS_TABLE_NAME,
    METADATA_SENSOR_CHECKPOINTS_TABLE_NAME,
    METADATA_SENSOR_LEASES_TABLE_NAME,
    METADATA_SENSOR_OVERRIDES_TABLE_NAME,
    METADATA_SENSOR_STEPS_TABLE_NAME,
    METADATA_SENSOR_TICKS_TABLE_NAME,
    REPLAY_VALUE_KIND_INTEGER,
    REPLAY_VALUE_KIND_TIMESTAMP,
    VIRTUAL_OBJECT_STATE_KIND_DEPLOYMENT,
)
from streambuild.adapter.exceptions import AdapterResultError, AdapterWarehouseError
from streambuild.adapter.models import (
    AdapterCurrentQualityNode,
    AdapterDeploymentRecord,
    AdapterDeploymentWatermarkRecord,
    AdapterDirectFingerprintRecord,
    AdapterDirectFingerprintSnapshot,
    AdapterInvocationRecord,
    AdapterManifest,
    AdapterManifestResource,
    AdapterManifestSnapshot,
    AdapterMetadataState,
    AdapterNodeResultRecord,
    AdapterObjectStateRecord,
    AdapterPublishEventRecord,
    AdapterQueryResult,
    AdapterRunEventRecord,
    AdapterRunStatementRecord,
    AdapterSensorCheckpointRecord,
    AdapterSensorLeaseRecord,
    AdapterSensorOverrideRecord,
    AdapterSensorState,
    AdapterSensorStepRecord,
    AdapterSensorTickRecord,
)
from streambuild.adapter.types import AdapterOptionalStateStatus, AdapterReplayBoundaryMode
from streambuild.adapters.clickhouse.models import ClickHouseMetadataStatement

_CURRENT_STATE_SCHEMA_VERSION: int = 7
_BOUNDARY_PART_COUNT: int = 2
_SNAPSHOT_FIELD_NAMES: tuple[str, ...] = (
    "binding_key",
    "definition_fingerprint",
    "execution_fingerprint",
    "status",
    "severity",
    "failure_count",
    "completed_at",
    "payload_json",
    "error_message",
    "cadence_seconds",
    "warmup_seconds",
    "result_id",
)
_SNAPSHOT_COLUMNS_SQL: str = ", ".join(
    f"tupleElement(snapshot, {position}) AS {name}"
    for position, name in enumerate(_SNAPSHOT_FIELD_NAMES, start=1)
)
_SNAPSHOT_TUPLE_SQL: str = f"tuple({', '.join(_SNAPSHOT_FIELD_NAMES)})"
_LOGICAL_SNAPSHOT_TUPLE_SQL: str = (
    f"tuple({', '.join(f'logical.{name}' for name in _SNAPSHOT_FIELD_NAMES)})"
)
_DIRECT_FINGERPRINT_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "fingerprint_id",
        "logical_model_identity",
        "definition_sql",
        "definition_hash",
        "identity_metadata",
        "workflow_id",
        "tool_version",
        "applied_at",
    }
)
_MANIFEST_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "manifest_id",
        "invocation_id",
        "project_identity",
        "target_name",
        "target_database",
        "is_production",
        "project_revision",
        "manifest_fingerprint",
        "manifest_version",
        "pipelines",
        "resources",
        "tool_version",
        "published_at",
    }
)


def render_clickhouse_metadata_migration_statements(database: str) -> tuple[str, ...]:
    """Render the current additive ClickHouse metadata migration."""

    return (
        _render_object_state_table(database),
        _render_deployments_table(database),
        _render_deployment_watermarks_table(database),
        _render_publish_history_table(database),
        _render_direct_fingerprints_table(database),
        _render_invocations_table(database),
        _render_node_results_table(database),
        _render_run_events_table(database),
        _render_run_statements_table(database),
        _render_sensor_checkpoints_table(database),
        _render_sensor_ticks_table(database),
        _render_sensor_steps_table(database),
        _render_sensor_overrides_table(database),
        _render_sensor_leases_table(database),
        _render_manifests_table(database),
        f"DROP TABLE IF EXISTS {database}._streambuild_owned_resources SYNC",
        _render_publish_history_lifecycle_columns(database),
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
                "(publication_id, deployment_id, operation, previous_deployment_id, "
                "logical_database_name, logical_view_name, physical_database_name, "
                "physical_relation_name, published_at) VALUES"
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
                "(result_id, invocation_id, node_kind, node_name, binding_key, "
                "definition_fingerprint, execution_fingerprint, target_identity, trigger, "
                "scheduled_for, cadence_seconds, warmup_seconds, status, severity, "
                "failure_count, completed_at, payload_json, error_message) VALUES"
            ),
            rows=tuple(_node_result_row(record) for record in state.node_results),
        ),
    )


def load_clickhouse_direct_fingerprints(
    *,
    connection: AdapterConnection,
    database: str,
    logical_model_identities: tuple[str, ...],
) -> AdapterDirectFingerprintSnapshot:
    """Load latest compatible baselines without making them execution state."""

    try:
        columns: frozenset[str] = connection.metadata_columns(
            database=database,
            table=METADATA_DIRECT_FINGERPRINTS_TABLE_NAME,
        )
        if not columns:
            return AdapterDirectFingerprintSnapshot(
                status=AdapterOptionalStateStatus.ABSENT,
                baselines=(),
            )
        if not _DIRECT_FINGERPRINT_REQUIRED_COLUMNS <= columns:
            return AdapterDirectFingerprintSnapshot(
                status=AdapterOptionalStateStatus.UNAVAILABLE,
                baselines=(),
                warning="Direct SQL baseline table has an incompatible schema",
            )
        if not logical_model_identities:
            return AdapterDirectFingerprintSnapshot(
                status=AdapterOptionalStateStatus.AVAILABLE,
                baselines=(),
            )
        result: AdapterQueryResult = connection.query(
            _latest_fingerprints_query(
                database=database,
                logical_model_identities=logical_model_identities,
            )
        )
    except AdapterWarehouseError as error:
        return AdapterDirectFingerprintSnapshot(
            status=AdapterOptionalStateStatus.UNAVAILABLE,
            baselines=(),
            warning=f"Direct SQL baselines unavailable: {error}",
        )
    return AdapterDirectFingerprintSnapshot(
        status=AdapterOptionalStateStatus.AVAILABLE,
        baselines=tuple(
            AdapterDirectFingerprintRecord(
                fingerprint_id=str(row[0]),
                logical_model_identity=str(row[1]),
                definition_sql=str(row[2]),
                definition_hash=str(row[3]),
                identity_metadata=str(row[4]),
                workflow_id=str(row[5]),
                tool_version=str(row[6]),
                applied_at=str(row[7]),
            )
            for row in result.rows
        ),
    )


def render_clickhouse_direct_fingerprint_observations(
    *, database: str, fingerprints: tuple[AdapterDirectFingerprintRecord, ...]
) -> tuple[str, ...]:
    """Render best-effort schema initialization and logical baseline inserts."""

    if not fingerprints:
        return ()
    values: str = ",\n".join(_fingerprint_value(record) for record in fingerprints)
    return (
        f"CREATE DATABASE IF NOT EXISTS {database};",
        _terminate_sql(_render_direct_fingerprints_table(database)),
        (
            f"INSERT INTO {database}.{METADATA_DIRECT_FINGERPRINTS_TABLE_NAME} "
            "(fingerprint_id, logical_model_identity, definition_sql, definition_hash, "
            "identity_metadata, workflow_id, tool_version, applied_at) VALUES\n"
            f"{values};"
        ),
    )


def _latest_fingerprints_query(*, database: str, logical_model_identities: tuple[str, ...]) -> str:
    identities: str = ", ".join(
        _render_sql_literal(identity) for identity in logical_model_identities
    )
    table: str = f"{database}.{METADATA_DIRECT_FINGERPRINTS_TABLE_NAME}"
    return (
        "SELECT tuple_value.1, logical_model_identity, tuple_value.2, tuple_value.3, "
        "tuple_value.4, tuple_value.5, tuple_value.6, tuple_value.7 FROM ("
        "SELECT logical_model_identity, argMax(tuple(fingerprint_id, definition_sql, "
        "definition_hash, identity_metadata, workflow_id, tool_version, applied_at), "
        "tuple(applied_at, fingerprint_id)) AS tuple_value "
        f"FROM {table} WHERE logical_model_identity IN ({identities}) "
        "GROUP BY logical_model_identity) ORDER BY logical_model_identity"
    )


def _fingerprint_value(record: AdapterDirectFingerprintRecord) -> str:
    values: tuple[str, ...] = (
        record.fingerprint_id,
        record.logical_model_identity,
        record.definition_sql,
        record.definition_hash,
        record.identity_metadata,
        record.workflow_id,
        record.tool_version,
    )
    quoted: str = ", ".join(_render_sql_literal(value) for value in values)
    applied_at: str = (
        "now64(3, 'UTC')"
        if record.applied_at is None
        else f"toDateTime64({_render_sql_literal(record.applied_at)}, 3, 'UTC')"
    )
    return f"({quoted}, {applied_at})"


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
        "    operation LowCardinality(String) DEFAULT 'promote',\n"
        "    previous_deployment_id Nullable(String),\n"
        "    logical_database_name String,\n"
        "    logical_view_name String,\n"
        "    physical_database_name String,\n"
        "    physical_relation_name String,\n"
        "    published_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (publication_id, logical_database_name, logical_view_name)"
    )


def _render_publish_history_lifecycle_columns(database: str) -> str:
    return (
        f"ALTER TABLE {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME} "
        "ADD COLUMN IF NOT EXISTS operation LowCardinality(String) DEFAULT 'promote' "
        "AFTER deployment_id, ADD COLUMN IF NOT EXISTS previous_deployment_id Nullable(String) "
        "AFTER operation"
    )


def _render_direct_fingerprints_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_DIRECT_FINGERPRINTS_TABLE_NAME} (\n"
        "    fingerprint_id String,\n"
        "    logical_model_identity String,\n"
        "    definition_sql String,\n"
        "    definition_hash String,\n"
        "    identity_metadata String,\n"
        "    workflow_id String,\n"
        "    tool_version String,\n"
        "    applied_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree ORDER BY (logical_model_identity, applied_at, fingerprint_id)"
    )


def _render_manifests_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_MANIFESTS_TABLE_NAME} (\n"
        "    manifest_id String,\n"
        "    invocation_id String,\n"
        "    project_identity String,\n"
        "    target_name String,\n"
        "    target_database String,\n"
        "    is_production Bool,\n"
        "    project_revision Nullable(String),\n"
        "    manifest_fingerprint String,\n"
        "    manifest_version UInt64,\n"
        "    pipelines Array(String),\n"
        "    resources Array(Tuple(\n"
        "        pipeline_name String,\n"
        "        logical_type String,\n"
        "        logical_name String,\n"
        "        resource_role String,\n"
        "        resource_database String,\n"
        "        resource_name String,\n"
        "        resource_kind String\n"
        "    )),\n"
        "    tool_version String,\n"
        "    published_at DateTime64(6, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (project_identity, target_name, target_database, published_at, manifest_id)"
    )


def load_clickhouse_manifests(
    *,
    connection: AdapterConnection,
    database: str,
    project_identity: str,
    target_name: str,
    target_database: str,
) -> AdapterManifestSnapshot:
    """Load complete manifest history for one project target, newest first."""

    try:
        columns: frozenset[str] = connection.metadata_columns(
            database=database,
            table=METADATA_MANIFESTS_TABLE_NAME,
        )
        if not columns:
            return AdapterManifestSnapshot(status="absent", manifests=())
        if not _MANIFEST_REQUIRED_COLUMNS <= columns:
            return AdapterManifestSnapshot(
                status="unavailable",
                manifests=(),
                warning="Manifest table has an incompatible schema",
            )
        result: AdapterQueryResult = connection.query(
            _manifest_history_query(
                database=database,
                project_identity=project_identity,
                target_name=target_name,
                target_database=target_database,
            )
        )
    except AdapterWarehouseError as error:
        return AdapterManifestSnapshot(
            status="unavailable",
            manifests=(),
            warning=f"Manifest history unavailable: {error}",
        )
    manifests: tuple[AdapterManifest, ...] = tuple(_manifest_from_row(row) for row in result.rows)
    return AdapterManifestSnapshot(status="available", manifests=manifests)


def _manifest_from_row(row: tuple[object, ...]) -> AdapterManifest:
    pipelines: tuple[str, ...] = tuple(str(pipeline) for pipeline in cast(Sequence[object], row[9]))
    resources: tuple[AdapterManifestResource, ...] = tuple(
        _manifest_resource(resource) for resource in cast(Sequence[object], row[10])
    )
    project_revision: str | None = None if row[6] is None else str(row[6])
    return AdapterManifest(
        manifest_id=str(row[0]),
        invocation_id=str(row[1]),
        project_identity=str(row[2]),
        target_name=str(row[3]),
        target_database=str(row[4]),
        is_production=bool(row[5]),
        project_revision=project_revision,
        manifest_fingerprint=str(row[7]),
        manifest_version=int(cast(int, row[8])),
        pipelines=pipelines,
        resources=resources,
        tool_version=str(row[11]),
        published_at=str(row[12]),
    )


def _manifest_resource(resource: object) -> AdapterManifestResource:
    names: tuple[str, ...] = (
        "pipeline_name",
        "logical_type",
        "logical_name",
        "resource_role",
        "resource_database",
        "resource_name",
        "resource_kind",
    )
    if isinstance(resource, Mapping):
        mapping: Mapping[str, object] = cast(Mapping[str, object], resource)
        values: tuple[object, ...] = tuple(mapping[name] for name in names)
    elif isinstance(resource, Sequence) and not isinstance(resource, str | bytes):
        values = tuple(resource)
    else:
        raise AdapterResultError("Manifest resource row is not a tuple")
    if len(values) != len(names):
        raise AdapterResultError("Manifest resource row has an incompatible shape")
    return AdapterManifestResource(
        pipeline_name=str(values[0]),
        logical_type=str(values[1]),
        logical_name=str(values[2]),
        resource_role=str(values[3]),
        resource_database=str(values[4]),
        resource_name=str(values[5]),
        resource_kind=str(values[6]),
    )


def _manifest_history_query(
    *,
    database: str,
    project_identity: str,
    target_name: str,
    target_database: str,
) -> str:
    table: str = f"{database}.{METADATA_MANIFESTS_TABLE_NAME}"
    source: str = f"{table} AS manifest"
    return (
        "SELECT manifest.manifest_id, manifest.invocation_id, manifest.project_identity, "
        "manifest.target_name, manifest.target_database, manifest.is_production, "
        "manifest.project_revision, manifest.manifest_fingerprint, manifest.manifest_version, "
        "manifest.pipelines, manifest.resources, manifest.tool_version, manifest.published_at "
        f"FROM {source} "
        f"WHERE manifest.project_identity = {_render_sql_literal(project_identity)} "
        f"AND manifest.target_name = {_render_sql_literal(target_name)} "
        f"AND manifest.target_database = {_render_sql_literal(target_database)} "
        "ORDER BY manifest.published_at DESC, manifest.manifest_id DESC"
    )


def render_clickhouse_manifest_publication(
    *, database: str, manifest: AdapterManifest
) -> tuple[str, ...]:
    """Render one append containing a complete immutable manifest."""

    columns: str = (
        "manifest_id, invocation_id, project_identity, target_name, target_database, "
        "is_production, project_revision, manifest_fingerprint, manifest_version, pipelines, "
        "resources, tool_version, published_at"
    )
    strings: tuple[str, ...] = (
        manifest.manifest_id,
        manifest.invocation_id,
        manifest.project_identity,
        manifest.target_name,
        manifest.target_database,
    )
    pipelines: str = (
        "[" + ", ".join(_render_sql_literal(pipeline) for pipeline in manifest.pipelines) + "]"
    )
    rendered_resources: tuple[str, ...] = tuple(
        _render_manifest_resource(resource) for resource in manifest.resources
    )
    resources: str = "[" + ", ".join(rendered_resources) + "]"
    revision: str = (
        "NULL"
        if manifest.project_revision is None
        else _render_sql_literal(manifest.project_revision)
    )
    values: str = ", ".join(_render_sql_literal(value) for value in strings)
    return (
        f"INSERT INTO {database}.{METADATA_MANIFESTS_TABLE_NAME} ({columns}) VALUES\n"
        f"({values}, {str(manifest.is_production).lower()}, {revision}, "
        f"{_render_sql_literal(manifest.manifest_fingerprint)}, {manifest.manifest_version}, "
        f"{pipelines}, {resources}, {_render_sql_literal(manifest.tool_version)}, "
        f"toDateTime64({_render_sql_literal(manifest.published_at)}, 6, 'UTC'));",
    )


def _render_manifest_resource(resource: AdapterManifestResource) -> str:
    values: tuple[str, ...] = (
        resource.pipeline_name,
        resource.logical_type,
        resource.logical_name,
        resource.resource_role,
        resource.resource_database,
        resource.resource_name,
        resource.resource_kind,
    )
    literals: tuple[str, ...] = tuple(_render_sql_literal(value) for value in values)
    return f"({', '.join(literals)})"


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
        "    node_name String,\n"
        "    binding_key String,\n"
        "    definition_fingerprint String,\n"
        "    execution_fingerprint String,\n"
        "    target_identity String,\n"
        "    trigger LowCardinality(String),\n"
        "    scheduled_for Nullable(DateTime64(3, 'UTC')),\n"
        "    cadence_seconds Nullable(UInt64),\n"
        "    warmup_seconds UInt64,\n"
        "    status LowCardinality(String),\n"
        "    severity Nullable(String),\n"
        "    failure_count UInt64,\n"
        "    completed_at DateTime64(3, 'UTC'),\n"
        "    payload_json String,\n"
        "    error_message Nullable(String)\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (node_kind, node_name, completed_at, result_id)"
    )


def _render_run_events_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_RUN_EVENTS_TABLE_NAME} (\n"
        "    invocation_id String,\n"
        "    sequence UInt64,\n"
        "    emitted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC'),\n"
        "    event_kind LowCardinality(String),\n"
        "    step_id Nullable(String),\n"
        "    phase Nullable(String),\n"
        "    payload_json String\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (invocation_id, sequence)"
    )


def _render_run_statements_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_RUN_STATEMENTS_TABLE_NAME} (\n"
        "    invocation_id String,\n"
        "    statement_sequence UInt64,\n"
        "    step_id String,\n"
        "    phase LowCardinality(String),\n"
        "    intent LowCardinality(String),\n"
        "    sql String,\n"
        "    sql_sha256 FixedString(64),\n"
        "    workflow_sha256 FixedString(64),\n"
        "    workflow_revision UInt64,\n"
        "    recorded_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')\n"
        ") ENGINE = ReplacingMergeTree(workflow_revision)\n"
        "ORDER BY (invocation_id, statement_sequence)"
    )


def _render_sensor_checkpoints_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_SENSOR_CHECKPOINTS_TABLE_NAME} (\n"
        "    sensor_name String,\n"
        "    source LowCardinality(String),\n"
        "    position_completed_at DateTime64(3, 'UTC'),\n"
        "    position_result_id String,\n"
        "    recorded_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (sensor_name, source, position_completed_at, position_result_id)"
    )


def _render_sensor_ticks_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} (\n"
        "    tick_id String,\n"
        "    sensor_name String,\n"
        "    definition_fingerprint String,\n"
        "    kind LowCardinality(String),\n"
        "    event_id Nullable(String),\n"
        "    event_kind Nullable(String),\n"
        "    attempt UInt32,\n"
        "    status LowCardinality(String),\n"
        "    started_at DateTime64(3, 'UTC'),\n"
        "    completed_at Nullable(DateTime64(3, 'UTC')),\n"
        "    error_message Nullable(String),\n"
        "    skip_reason Nullable(String),\n"
        "    cursor Nullable(String)\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (sensor_name, started_at, tick_id)"
    )


def _render_sensor_steps_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_SENSOR_STEPS_TABLE_NAME} (\n"
        "    sensor_name String,\n"
        "    event_id String,\n"
        "    step_key String,\n"
        "    policy LowCardinality(String),\n"
        "    status LowCardinality(String),\n"
        "    attempt UInt32,\n"
        "    result_json Nullable(String),\n"
        "    error_message Nullable(String),\n"
        "    recorded_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (sensor_name, event_id, step_key, recorded_at)"
    )


def _render_sensor_overrides_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_SENSOR_OVERRIDES_TABLE_NAME} (\n"
        "    override_id String,\n"
        "    sensor_name String,\n"
        "    status LowCardinality(String),\n"
        "    actor Nullable(String),\n"
        "    changed_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (sensor_name, changed_at, override_id)"
    )


def _render_sensor_leases_table(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_SENSOR_LEASES_TABLE_NAME} (\n"
        "    lease_name String,\n"
        "    owner_id String,\n"
        "    acquired_at DateTime64(3, 'UTC'),\n"
        "    expires_at DateTime64(3, 'UTC')\n"
        ") ENGINE = MergeTree\n"
        "ORDER BY (lease_name, acquired_at, owner_id)"
    )


def render_clickhouse_sensor_state_inserts(
    *,
    database: str,
    state: AdapterSensorState,
    include_migration: bool = False,
) -> tuple[str, ...]:
    """Render incremental sensor-state inserts, optionally preceded by the migration."""

    statements: tuple[ClickHouseMetadataStatement, ...] = (
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_SENSOR_CHECKPOINTS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_SENSOR_CHECKPOINTS_TABLE_NAME} "
                "(sensor_name, source, position_completed_at, position_result_id) VALUES"
            ),
            rows=tuple(_sensor_checkpoint_row(record) for record in state.checkpoints),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_SENSOR_TICKS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} "
                "(tick_id, sensor_name, definition_fingerprint, kind, event_id, event_kind, "
                "attempt, status, started_at, completed_at, error_message, skip_reason, "
                "cursor) VALUES"
            ),
            rows=tuple(_sensor_tick_row(record) for record in state.ticks),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_SENSOR_STEPS_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_SENSOR_STEPS_TABLE_NAME} "
                "(sensor_name, event_id, step_key, policy, status, attempt, result_json, "
                "error_message) VALUES"
            ),
            rows=tuple(_sensor_step_row(record) for record in state.steps),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_SENSOR_OVERRIDES_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_SENSOR_OVERRIDES_TABLE_NAME} "
                "(override_id, sensor_name, status, actor) VALUES"
            ),
            rows=tuple(_sensor_override_row(record) for record in state.overrides),
        ),
        ClickHouseMetadataStatement(
            table=f"{database}.{METADATA_SENSOR_LEASES_TABLE_NAME}",
            sql=(
                f"INSERT INTO {database}.{METADATA_SENSOR_LEASES_TABLE_NAME} "
                "(lease_name, owner_id, acquired_at, expires_at) VALUES"
            ),
            rows=tuple(_sensor_lease_row(record) for record in state.leases),
        ),
    )
    inserts: tuple[str, ...] = tuple(
        _render_insert_statement(statement) for statement in statements if statement.rows
    )
    if not include_migration:
        return inserts
    return (*render_clickhouse_metadata_migration_workflow(database), *inserts)


def _sensor_checkpoint_row(record: AdapterSensorCheckpointRecord) -> dict[str, object]:
    return {
        "sensor_name": record.sensor_name,
        "source": record.source,
        "position_completed_at": record.position_completed_at,
        "position_result_id": record.position_result_id,
    }


def _sensor_tick_row(record: AdapterSensorTickRecord) -> dict[str, object]:
    return {
        "tick_id": record.tick_id,
        "sensor_name": record.sensor_name,
        "definition_fingerprint": record.definition_fingerprint,
        "kind": record.kind,
        "event_id": record.event_id,
        "event_kind": record.event_kind,
        "attempt": record.attempt,
        "status": record.status,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "error_message": record.error_message,
        "skip_reason": record.skip_reason,
        "cursor": record.cursor,
    }


def _sensor_step_row(record: AdapterSensorStepRecord) -> dict[str, object]:
    return {
        "sensor_name": record.sensor_name,
        "event_id": record.event_id,
        "step_key": record.step_key,
        "policy": record.policy,
        "status": record.status,
        "attempt": record.attempt,
        "result_json": record.result_json,
        "error_message": record.error_message,
    }


def _sensor_override_row(record: AdapterSensorOverrideRecord) -> dict[str, object]:
    return {
        "override_id": record.override_id,
        "sensor_name": record.sensor_name,
        "status": record.status,
        "actor": record.actor,
    }


def _sensor_lease_row(record: AdapterSensorLeaseRecord) -> dict[str, object]:
    return {
        "lease_name": record.lease_name,
        "owner_id": record.owner_id,
        "acquired_at": record.acquired_at,
        "expires_at": record.expires_at,
    }


def render_clickhouse_sensor_retention_cleanup(
    *, database: str, retention_days: int
) -> tuple[str, ...]:
    """Render bounded deletes for aged sensor ticks and steps; zero keeps everything."""

    if retention_days <= 0:
        return ()
    horizon: str = f"now64(3, 'UTC') - INTERVAL {int(retention_days)} DAY"
    return (
        (
            f"ALTER TABLE {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} "
            f"DELETE WHERE started_at < {horizon};"
        ),
        (
            f"ALTER TABLE {database}.{METADATA_SENSOR_STEPS_TABLE_NAME} "
            f"DELETE WHERE recorded_at < {horizon};"
        ),
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
            "(invocation_id, sequence, event_kind, step_id, phase, "
            "payload_json) VALUES"
        ),
        rows=tuple(_run_event_row(record) for record in events),
    )
    inserts: tuple[str, ...] = (_render_insert_statement(statement),)
    if not include_migration:
        return inserts
    return (*render_clickhouse_metadata_migration_workflow(database), *inserts)


def render_clickhouse_run_statement_inserts(
    *,
    database: str,
    statements: tuple[AdapterRunStatementRecord, ...],
    include_migration: bool = False,
) -> tuple[str, ...]:
    """Render one complete run statement set before warehouse execution."""

    if not statements:
        return ()
    statement: ClickHouseMetadataStatement = ClickHouseMetadataStatement(
        table=f"{database}.{METADATA_RUN_STATEMENTS_TABLE_NAME}",
        sql=(
            f"INSERT INTO {database}.{METADATA_RUN_STATEMENTS_TABLE_NAME} "
            "(invocation_id, statement_sequence, step_id, phase, intent, sql, "
            "sql_sha256, workflow_sha256, workflow_revision) VALUES"
        ),
        rows=tuple(_run_statement_row(record) for record in statements),
    )
    inserts: tuple[str, ...] = (_render_insert_statement(statement),)
    if not include_migration:
        return inserts
    return (*render_clickhouse_metadata_migration_workflow(database), *inserts)


def _run_statement_row(record: AdapterRunStatementRecord) -> dict[str, object]:
    return {
        "invocation_id": record.invocation_id,
        "statement_sequence": record.statement_sequence,
        "step_id": record.step_id,
        "phase": record.phase,
        "intent": record.intent,
        "sql": record.sql,
        "sql_sha256": record.sql_sha256,
        "workflow_sha256": record.workflow_sha256,
        "workflow_revision": record.workflow_revision,
    }


def _run_event_row(record: AdapterRunEventRecord) -> dict[str, object]:
    return {
        "invocation_id": record.invocation_id,
        "sequence": record.sequence,
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
    publication_id: str = (
        record.publication_id
        or sha256(
            json.dumps(
                (
                    record.deployment_id,
                    record.published_at,
                    record.operation,
                    record.previous_deployment_id,
                    binding_identity,
                ),
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )
    return tuple(
        cast(
            dict[str, object],
            {
                "publication_id": publication_id,
                "deployment_id": record.deployment_id,
                "operation": record.operation,
                "previous_deployment_id": record.previous_deployment_id,
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
        "node_name": record.node_name,
        "binding_key": record.binding_key,
        "definition_fingerprint": record.definition_fingerprint,
        "execution_fingerprint": record.execution_fingerprint,
        "target_identity": record.target_identity,
        "trigger": record.trigger,
        "scheduled_for": record.scheduled_for,
        "cadence_seconds": record.cadence_seconds,
        "warmup_seconds": record.warmup_seconds,
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
    logical_project_identity: str = project_identity.rsplit("/", maxsplit=1)[-1]
    project_literal: str = _render_sql_literal(logical_project_identity)
    project_suffix_literal: str = _render_sql_literal(f"/{logical_project_identity}")
    return (
        f"WITH manifest_nodes AS ({manifest_sql}), logical_snapshots AS ("
        "SELECT result.node_kind AS node_kind, result.node_name AS node_name, "
        "argMax(tuple(result.binding_key, result.definition_fingerprint, "
        "result.execution_fingerprint, result.status, result.severity, result.failure_count, "
        "result.completed_at, result.payload_json, result.error_message, result.cadence_seconds, "
        "result.warmup_seconds, result.result_id), "
        "tuple(result.completed_at, result.result_id)) AS snapshot FROM "
        f"{database}.{METADATA_NODE_RESULTS_TABLE_NAME} AS result INNER JOIN "
        f"{database}.{METADATA_INVOCATIONS_TABLE_NAME} AS invocation ON "
        "invocation.invocation_id = result.invocation_id WHERE result.target_identity = "
        f"{_render_sql_literal(target_identity)} AND (invocation.project_identity = "
        f"{project_literal} OR endsWith(invocation.project_identity, {project_suffix_literal})) "
        "GROUP BY result.node_kind, result.node_name, "
        "result.binding_key, result.execution_fingerprint, "
        "ifNull(toString(result.scheduled_for), result.result_id)), "
        "logical_results AS ("
        f"SELECT node_kind, node_name, {_SNAPSHOT_COLUMNS_SQL} FROM logical_snapshots), "
        "latest_results AS ("
        f"SELECT node_kind, node_name, {_SNAPSHOT_COLUMNS_SQL} FROM ("
        f"SELECT node_kind, node_name, argMax({_SNAPSHOT_TUPLE_SQL}, "
        "tuple(completed_at, result_id)) AS snapshot "
        "FROM logical_results GROUP BY node_kind, node_name)), "
        "matching_results AS ("
        f"SELECT node_kind, node_name, {_SNAPSHOT_COLUMNS_SQL} FROM ("
        "SELECT logical.node_kind AS node_kind, logical.node_name AS node_name, "
        f"argMax({_LOGICAL_SNAPSHOT_TUPLE_SQL}, "
        "tuple(logical.completed_at, logical.result_id)) AS snapshot "
        "FROM logical_results AS logical INNER JOIN manifest_nodes AS manifest ON "
        "logical.node_kind = manifest.node_kind AND logical.node_name = manifest.node_name "
        "WHERE logical.binding_key = manifest.binding_key AND "
        "logical.definition_fingerprint = manifest.definition_fingerprint AND "
        "logical.execution_fingerprint = manifest.execution_fingerprint "
        "GROUP BY logical.node_kind, logical.node_name)) "
        "SELECT manifest.node_kind AS node_kind, manifest.node_name AS node_name, "
        "manifest.binding_key AS binding_key, "
        "manifest.definition_fingerprint AS definition_fingerprint, "
        "manifest.execution_fingerprint AS execution_fingerprint, "
        "manifest.cadence_seconds AS cadence_seconds, "
        "manifest.warmup_seconds AS warmup_seconds, "
        "multiIf(latest.node_name = '', 'never_run', matching.node_name != '' AND ("
        "ifNull(matching.cadence_seconds, 0) != ifNull(manifest.cadence_seconds, 0) OR "
        "matching.warmup_seconds != manifest.warmup_seconds), 'schedule_changed', "
        "matching.node_name != '', matching.status, "
        "latest.binding_key != manifest.binding_key, "
        "'binding_changed', latest.definition_fingerprint != manifest.definition_fingerprint, "
        "'definition_changed', latest.execution_fingerprint != manifest.execution_fingerprint, "
        "'execution_changed', ifNull(latest.cadence_seconds, 0) != "
        "ifNull(manifest.cadence_seconds, 0) OR latest.warmup_seconds != "
        "manifest.warmup_seconds, "
        "'schedule_changed', latest.status) AS current_status, "
        "arrayFilter(reason -> reason != '', ["
        "if(matching.node_name = '' AND latest.node_name != '' AND "
        "latest.binding_key != manifest.binding_key, "
        "'binding_changed', ''), "
        "if(matching.node_name = '' AND latest.node_name != '' AND "
        "latest.definition_fingerprint != manifest.definition_fingerprint, "
        "'definition_changed', ''), "
        "if(matching.node_name = '' AND latest.node_name != '' AND "
        "latest.execution_fingerprint != manifest.execution_fingerprint, "
        "'execution_changed', ''), "
        "if(ifNull(matching.cadence_seconds, ifNull(latest.cadence_seconds, 0)) != "
        "ifNull(manifest.cadence_seconds, 0) OR "
        "ifNull(matching.warmup_seconds, latest.warmup_seconds) != manifest.warmup_seconds, "
        "'schedule_changed', '')]) AS drift_reasons, "
        "nullIf(if(matching.node_name != '', matching.severity, latest.severity), '') "
        "AS severity, "
        "if(matching.node_name != '', matching.failure_count, latest.failure_count) "
        "AS failure_count, "
        "if(matching.node_name != '', matching.completed_at, latest.completed_at) "
        "AS completed_at, "
        "if(matching.node_name != '', matching.payload_json, latest.payload_json) "
        "AS payload_json, "
        "nullIf(if(matching.node_name != '', matching.error_message, latest.error_message), '') "
        "AS error_message FROM manifest_nodes AS manifest "
        "LEFT JOIN latest_results AS latest ON latest.node_kind = manifest.node_kind AND "
        "latest.node_name = manifest.node_name LEFT JOIN matching_results AS matching ON "
        "matching.node_kind = manifest.node_kind AND matching.node_name = manifest.node_name "
        "ORDER BY manifest.node_kind, manifest.node_name"
    )


def _manifest_nodes_sql(nodes: tuple[AdapterCurrentQualityNode, ...]) -> str:
    if not nodes:
        return (
            "SELECT CAST('' AS String) AS node_kind, CAST('' AS String) AS node_name, "
            "CAST('' AS String) AS binding_key, CAST('' AS String) AS "
            "definition_fingerprint, CAST('' AS String) AS execution_fingerprint, "
            "CAST(NULL AS Nullable(UInt64)) AS cadence_seconds, "
            "CAST(0 AS UInt64) AS warmup_seconds WHERE false"
        )
    rows: str = ", ".join(
        f"({_render_sql_literal(node.node_kind)}, {_render_sql_literal(node.node_name)}, "
        f"{_render_sql_literal(node.binding_key)}, "
        f"{_render_sql_literal(node.definition_fingerprint)}, "
        f"{_render_sql_literal(node.execution_fingerprint)}, "
        f"{_render_sql_literal(node.cadence_seconds)}, {node.warmup_seconds})"
        for node in nodes
    )
    return (
        "SELECT * FROM VALUES('node_kind String, node_name String, binding_key String, "
        "definition_fingerprint String, execution_fingerprint String, "
        f"cadence_seconds Nullable(UInt64), warmup_seconds UInt64', {rows})"
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
