"""Load ClickHouse deployment inventory for lifecycle cleanup."""

import json
from collections.abc import Mapping
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    DEFAULT_REPLAY_LINEAGE_MODE,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
    METADATA_REPLAY_LINEAGE_MODE_COLUMN_NAME,
)
from streambuild.adapter.exceptions import AdapterRelationNotFoundError, AdapterResultError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterMetadataObjectKey,
    AdapterPreparedObjectMapping,
    AdapterPublishEventRecord,
    AdapterRelationCleanupRequest,
    AdapterStableBinding,
    AdapterStableBindingRemoval,
    AdapterStableView,
    CatalogRelation,
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapters.clickhouse.constants import CLICKHOUSE_VIEW_ENGINE
from streambuild.adapters.clickhouse.models import (
    ClickHouseDeploymentInventoryRow,
    ClickHousePublishEventInventoryRow,
)


def load_clickhouse_deployment_inventory(
    *, connection: AdapterConnection, database: str
) -> AdapterDeploymentInventory:
    """Load neutral deployment and publish-event records from ClickHouse metadata."""

    metadata_columns: frozenset[str] = connection.metadata_columns(
        database=database,
        table=METADATA_DEPLOYMENTS_TABLE_NAME,
    )
    replay_lineage_projection: str = (
        METADATA_REPLAY_LINEAGE_MODE_COLUMN_NAME
        if METADATA_REPLAY_LINEAGE_MODE_COLUMN_NAME in metadata_columns
        else (f"'{DEFAULT_REPLAY_LINEAGE_MODE}' AS {METADATA_REPLAY_LINEAGE_MODE_COLUMN_NAME}")
    )
    deployment_rows: tuple[ClickHouseDeploymentInventoryRow, ...] = _load_deployment_rows(
        connection=connection,
        database=database,
        replay_lineage_projection=replay_lineage_projection,
    )
    publish_rows: tuple[ClickHousePublishEventInventoryRow, ...] = _load_publish_rows(
        connection=connection,
        database=database,
    )
    return AdapterDeploymentInventory(
        deployments=tuple(_deployment_record(row) for row in deployment_rows),
        publish_events=tuple(_publish_event_record(row) for row in publish_rows),
    )


def _load_deployment_rows(
    *, connection: AdapterConnection, database: str, replay_lineage_projection: str
) -> tuple[ClickHouseDeploymentInventoryRow, ...]:
    try:
        return connection.query_many(
            statement=f"SELECT deployment_id, created_at, status, {replay_lineage_projection}, "
            "selected_root_keys_json, warning_codes_json, prepared_object_mappings_json "
            f"FROM {database}.{METADATA_DEPLOYMENTS_TABLE_NAME}",
            decode=_decode_deployment_row,
        )
    except AdapterRelationNotFoundError:
        return ()


def render_clickhouse_relation_cleanup(
    *, connection: AdapterConnection, request: AdapterRelationCleanupRequest
) -> tuple[str, ...]:
    """Render synchronous drops after guarding every relation against active use."""

    catalog: CatalogSnapshot = connection.load_catalog(request.database)
    statements: list[str] = []
    relation_name: str
    for relation_name in request.relation_names:
        current_state: InspectedManagedTableState = connection.inspect_managed_table_state(
            request.database
        )
        active_relation_names: frozenset[str] = frozenset(
            binding.physical_name for binding in current_state.active_bindings
        )
        if relation_name in active_relation_names:
            raise AdapterResultError(
                f"Refusing to clean active physical relation '{relation_name}'"
            )
        relation: CatalogRelation | None = catalog.relation(relation_name)
        relation_kind: str = (
            "VIEW"
            if relation is not None and relation.engine == CLICKHOUSE_VIEW_ENGINE
            else "TABLE"
        )
        statements.append(
            f"DROP {relation_kind} IF EXISTS {request.database}.{relation_name} SYNC;"
        )
    return tuple(statements)


def render_clickhouse_stable_binding_replacement(
    *, connection: AdapterConnection, request: AdapterBindingReplacementRequest
) -> tuple[str, ...]:
    """Render exact ClickHouse stable-binding replacements and removals."""

    statements: list[str] = []
    binding: AdapterStableBinding
    for binding in request.bindings:
        rendered_binding: str = connection.render_resource(
            database=binding.database,
            resource=AdapterStableView(
                name=binding.logical_name,
                target_relation_name=binding.physical_name,
            ),
        )
        statements.append(_terminate_sql(rendered_binding))
    removal: AdapterStableBindingRemoval
    for removal in request.removals:
        statements.append(f"DROP VIEW IF EXISTS {removal.database}.{removal.logical_name} SYNC;")
    return tuple(statements)


def _terminate_sql(statement: str) -> str:
    return f"{statement.rstrip().rstrip(';')};"


def _load_publish_rows(
    *, connection: AdapterConnection, database: str
) -> tuple[ClickHousePublishEventInventoryRow, ...]:
    try:
        return connection.query_many(
            statement="SELECT deployment_id, published_at, logical_view_names_json "
            f"FROM {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME}",
            decode=_decode_publish_event_row,
        )
    except AdapterRelationNotFoundError:
        return ()


def _deployment_record(row: ClickHouseDeploymentInventoryRow) -> AdapterDeploymentRecord:
    selected_root_payloads: list[dict[str, object]] = json.loads(row.selected_root_keys_json)
    warning_codes: list[object] = json.loads(row.warning_codes_json)
    mapping_payloads: list[dict[str, object]] = json.loads(row.prepared_object_mappings_json)
    return AdapterDeploymentRecord(
        deployment_id=row.deployment_id,
        created_at=row.created_at,
        status=row.status,
        replay_lineage_mode=row.replay_lineage_mode,
        selected_root_keys=tuple(_object_key(payload) for payload in selected_root_payloads),
        warning_codes=tuple(str(code) for code in warning_codes),
        prepared_object_mappings=tuple(
            AdapterPreparedObjectMapping(
                logical_key=_object_key(cast(dict[str, object], payload["logical_key"])),
                physical_name=str(payload["physical_name"]),
                logical_model_name=str(payload["logical_model_name"]),
            )
            for payload in mapping_payloads
        ),
    )


def _publish_event_record(
    row: ClickHousePublishEventInventoryRow,
) -> AdapterPublishEventRecord:
    logical_view_names: list[object] = json.loads(row.logical_view_names_json)
    return AdapterPublishEventRecord(
        deployment_id=row.deployment_id,
        published_at=row.published_at,
        logical_view_names=tuple(str(name) for name in logical_view_names),
    )


def _object_key(payload: dict[str, object]) -> AdapterMetadataObjectKey:
    database_value: object = payload["database"]
    return AdapterMetadataObjectKey(
        database=None if database_value is None else str(database_value),
        object_type=str(payload["object_type"]),
        name=str(payload["name"]),
    )


def _decode_deployment_row(row: Mapping[str, object]) -> ClickHouseDeploymentInventoryRow:
    return ClickHouseDeploymentInventoryRow(
        deployment_id=str(row["deployment_id"]),
        created_at=str(row["created_at"]),
        status=str(row["status"]),
        replay_lineage_mode=str(row["replay_lineage_mode"]),
        selected_root_keys_json=str(row["selected_root_keys_json"]),
        warning_codes_json=str(row["warning_codes_json"]),
        prepared_object_mappings_json=str(row["prepared_object_mappings_json"]),
    )


def _decode_publish_event_row(
    row: Mapping[str, object],
) -> ClickHousePublishEventInventoryRow:
    return ClickHousePublishEventInventoryRow(
        deployment_id=str(row["deployment_id"]),
        published_at=str(row["published_at"]),
        logical_view_names_json=str(row["logical_view_names_json"]),
    )
