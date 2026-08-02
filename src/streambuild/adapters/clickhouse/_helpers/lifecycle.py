"""Load ClickHouse deployment inventory for lifecycle cleanup."""

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_OBJECT_STATE_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
    VIRTUAL_DEPLOYMENT_STATUS_INCOMPLETE,
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
    ClickHouseObjectStateInventoryRow,
    ClickHousePublishEventInventoryRow,
)


def load_clickhouse_deployment_inventory(
    *, connection: AdapterConnection, database: str
) -> AdapterDeploymentInventory:
    """Load neutral deployment and publish-event records from ClickHouse metadata."""

    deployment_rows: tuple[ClickHouseDeploymentInventoryRow, ...] = _load_deployment_rows(
        connection=connection,
        database=database,
    )
    object_rows: tuple[ClickHouseObjectStateInventoryRow, ...] = _load_object_rows(
        connection=connection, database=database
    )
    publish_rows: tuple[ClickHousePublishEventInventoryRow, ...] = _load_publish_rows(
        connection=connection,
        database=database,
    )
    inventory_rows: tuple[ClickHouseDeploymentInventoryRow, ...] = _inventory_deployment_rows(
        deployment_rows=deployment_rows,
        object_rows=object_rows,
    )
    return AdapterDeploymentInventory(
        deployments=tuple(
            _deployment_record(row=row, object_rows=object_rows, publish_rows=publish_rows)
            for row in inventory_rows
        ),
        publish_events=_publish_event_records(publish_rows),
    )


def _load_deployment_rows(
    *, connection: AdapterConnection, database: str
) -> tuple[ClickHouseDeploymentInventoryRow, ...]:
    try:
        return connection.query_many(
            statement="SELECT deployment_id, created_at, replay_lineage_mode "
            f"FROM {database}.{METADATA_DEPLOYMENTS_TABLE_NAME}",
            decode=_decode_deployment_row,
        )
    except AdapterRelationNotFoundError:
        return ()


def _load_object_rows(
    *, connection: AdapterConnection, database: str
) -> tuple[ClickHouseObjectStateInventoryRow, ...]:
    try:
        return connection.query_many(
            statement="SELECT DISTINCT deployment_id, logical_database_name, logical_object_type, "
            "logical_object_name, physical_relation_name, logical_model_name, is_selected_root "
            ", observed_at "
            f"FROM {database}.{METADATA_OBJECT_STATE_TABLE_NAME} "
            "WHERE state_kind = 'deployment' AND deployment_id IS NOT NULL",
            decode=_decode_object_state_row,
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
            statement="SELECT DISTINCT publication_id, deployment_id, published_at, "
            "logical_database_name, logical_view_name, physical_relation_name "
            f"FROM {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME}",
            decode=_decode_publish_event_row,
        )
    except AdapterRelationNotFoundError:
        return ()


def _deployment_record(
    *,
    row: ClickHouseDeploymentInventoryRow,
    object_rows: tuple[ClickHouseObjectStateInventoryRow, ...],
    publish_rows: tuple[ClickHousePublishEventInventoryRow, ...],
) -> AdapterDeploymentRecord:
    deployment_objects: tuple[ClickHouseObjectStateInventoryRow, ...] = tuple(
        object_row for object_row in object_rows if object_row.deployment_id == row.deployment_id
    )
    return AdapterDeploymentRecord(
        deployment_id=row.deployment_id,
        created_at=row.created_at,
        status=(
            VIRTUAL_DEPLOYMENT_STATUS_INCOMPLETE
            if not row.header_present
            else (
                "published"
                if any(event.deployment_id == row.deployment_id for event in publish_rows)
                else "staged"
            )
        ),
        replay_lineage_mode=row.replay_lineage_mode,
        selected_root_keys=tuple(
            _object_key_from_row(object_row)
            for object_row in deployment_objects
            if object_row.is_selected_root
        ),
        warning_codes=(),
        prepared_object_mappings=tuple(
            AdapterPreparedObjectMapping(
                logical_key=_object_key_from_row(object_row),
                physical_name=str(object_row.physical_name),
                logical_model_name=str(object_row.logical_model_name),
            )
            for object_row in deployment_objects
            if object_row.physical_name is not None and object_row.logical_model_name is not None
        ),
    )


def _inventory_deployment_rows(
    *,
    deployment_rows: tuple[ClickHouseDeploymentInventoryRow, ...],
    object_rows: tuple[ClickHouseObjectStateInventoryRow, ...],
) -> tuple[ClickHouseDeploymentInventoryRow, ...]:
    persisted_ids: frozenset[str] = frozenset(row.deployment_id for row in deployment_rows)
    headerless_ids: tuple[str, ...] = tuple(
        sorted({row.deployment_id for row in object_rows if row.deployment_id not in persisted_ids})
    )
    headerless_rows: list[ClickHouseDeploymentInventoryRow] = []
    deployment_id: str
    for deployment_id in headerless_ids:
        observed_times: tuple[str, ...] = tuple(
            row.observed_at for row in object_rows if row.deployment_id == deployment_id
        )
        headerless_rows.append(
            ClickHouseDeploymentInventoryRow(
                deployment_id=deployment_id,
                created_at=min(observed_times),
                replay_lineage_mode="unknown",
                header_present=False,
            )
        )
    return (*deployment_rows, *headerless_rows)


def _publish_event_records(
    rows: tuple[ClickHousePublishEventInventoryRow, ...],
) -> tuple[AdapterPublishEventRecord, ...]:
    publication_ids: tuple[str, ...] = tuple(sorted({row.publication_id for row in rows}))
    return tuple(
        _publish_event_record(_publication_rows(rows=rows, publication_id=publication_id))
        for publication_id in publication_ids
    )


def _publication_rows(
    *, rows: tuple[ClickHousePublishEventInventoryRow, ...], publication_id: str
) -> tuple[ClickHousePublishEventInventoryRow, ...]:
    return tuple(row for row in rows if row.publication_id == publication_id)


def _publish_event_record(
    rows: tuple[ClickHousePublishEventInventoryRow, ...],
) -> AdapterPublishEventRecord:
    first: ClickHousePublishEventInventoryRow = rows[0]
    return AdapterPublishEventRecord(
        deployment_id=first.deployment_id,
        published_at=first.published_at,
        logical_view_names=tuple(row.logical_view_name for row in rows),
        bindings=tuple(
            AdapterStableBinding(
                database=row.database_name,
                logical_name=row.logical_view_name,
                physical_name=row.physical_relation_name,
            )
            for row in rows
        ),
    )


def _object_key_from_row(row: ClickHouseObjectStateInventoryRow) -> AdapterMetadataObjectKey:
    return AdapterMetadataObjectKey(
        database=row.database_name,
        object_type=row.object_type,
        name=row.object_name,
    )


def _decode_deployment_row(row: Mapping[str, object]) -> ClickHouseDeploymentInventoryRow:
    return ClickHouseDeploymentInventoryRow(
        deployment_id=str(row["deployment_id"]),
        created_at=str(row["created_at"]),
        replay_lineage_mode=str(row["replay_lineage_mode"]),
    )


def _decode_object_state_row(row: Mapping[str, object]) -> ClickHouseObjectStateInventoryRow:
    return ClickHouseObjectStateInventoryRow(
        deployment_id=str(row["deployment_id"]),
        database_name=(
            None if row["logical_database_name"] is None else str(row["logical_database_name"])
        ),
        object_type=str(row["logical_object_type"]),
        object_name=str(row["logical_object_name"]),
        physical_name=(
            None if row["physical_relation_name"] is None else str(row["physical_relation_name"])
        ),
        logical_model_name=(
            None if row["logical_model_name"] is None else str(row["logical_model_name"])
        ),
        is_selected_root=bool(row["is_selected_root"]),
        observed_at=str(row["observed_at"]),
    )


def _decode_publish_event_row(
    row: Mapping[str, object],
) -> ClickHousePublishEventInventoryRow:
    return ClickHousePublishEventInventoryRow(
        publication_id=str(row["publication_id"]),
        deployment_id=str(row["deployment_id"]),
        published_at=str(row["published_at"]),
        database_name=str(row["logical_database_name"]),
        logical_view_name=str(row["logical_view_name"]),
        physical_relation_name=str(row["physical_relation_name"]),
    )
