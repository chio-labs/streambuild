"""Load persisted object state into one planning warehouse snapshot."""

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import METADATA_OBJECT_STATE_TABLE_NAME
from streambuild.adapter.exceptions import AdapterRelationNotFoundError
from streambuild.adapter.models import (
    AdapterDeploymentRecord,
    AdapterDeploymentRuntimeDetailRecord,
    AdapterDeploymentWatermarkRecord,
    AdapterMetadataObjectKey,
    AdapterMetadataState,
    AdapterObjectStateRecord,
    AdapterPreparedObjectMapping,
    AdapterPublishEventRecord,
)
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.compiler.planner.models import (
    DeploymentRecord,
    MetadataState,
    ObjectStateMetadataRow,
    ObjectStateRecord,
    PreparedObjectMapping,
)


def load_all_object_state_records(
    *,
    client: AdapterConnection,
    metadata_database: str,
) -> tuple[ObjectStateRecord, ...]:
    """Load every persisted object-state row into one planning snapshot."""

    try:
        rows: tuple[ObjectStateMetadataRow, ...] = client.query_many(
            statement="SELECT deployment_id, database_name, object_type, object_name, "
            "normalized_fingerprint, normalized_query, recorded_at "
            f"FROM {metadata_database}.{METADATA_OBJECT_STATE_TABLE_NAME}",
            decode=_decode_object_state_metadata_row,
        )
    except AdapterRelationNotFoundError:
        return ()
    return tuple(
        ObjectStateRecord(
            deployment_id=row.deployment_id,
            key=ObjectKey(
                database=row.database_name,
                object_type=row.object_type,
                name=row.object_name,
            ),
            normalized_fingerprint=row.normalized_fingerprint,
            normalized_query=row.normalized_query,
            recorded_at=row.recorded_at,
        )
        for row in rows
    )


def build_adapter_metadata_state(state: MetadataState) -> AdapterMetadataState:
    """Convert logical metadata records into the neutral persistence contract."""

    return AdapterMetadataState(
        object_states=tuple(
            AdapterObjectStateRecord(
                deployment_id=record.deployment_id,
                key=_adapter_key(record.key),
                normalized_fingerprint=record.normalized_fingerprint,
                normalized_query=record.normalized_query,
                recorded_at=record.recorded_at,
            )
            for record in state.object_states
        ),
        deployments=tuple(_adapter_deployment(record) for record in state.deployments),
        deployment_watermarks=tuple(
            AdapterDeploymentWatermarkRecord(
                deployment_id=record.deployment_id,
                root_key=_adapter_key(record.root_key),
                anchor_key=_adapter_key(record.anchor_key),
                boundary_key=record.boundary_key,
                cutoff_value=record.cutoff_value,
            )
            for record in state.deployment_watermarks
        ),
        deployment_runtime_details=tuple(
            AdapterDeploymentRuntimeDetailRecord(
                deployment_id=record.deployment_id,
                root_key=_adapter_key(record.root_key),
                state_kind=record.state_kind,
                replay_strategy=record.replay_strategy,
                active_deployment_id=record.active_deployment_id,
                anchor_key=_adapter_key(record.anchor_key),
                anchor_physical_name=record.anchor_physical_name,
                execution_mode=record.execution_mode,
                configured_backfill_mode=record.configured_backfill_mode,
                execution_lookback_seconds=record.execution_lookback_seconds,
                live_target_names=record.live_target_names,
            )
            for record in state.deployment_runtime_details
        ),
        publish_events=tuple(
            AdapterPublishEventRecord(
                deployment_id=record.deployment_id,
                published_at=record.published_at,
                logical_view_names=record.logical_view_names,
            )
            for record in state.publish_events
        ),
    )


def _decode_object_state_metadata_row(row: Mapping[str, object]) -> ObjectStateMetadataRow:
    return ObjectStateMetadataRow(
        deployment_id=str(row["deployment_id"]),
        database_name=None if row["database_name"] is None else str(row["database_name"]),
        object_type=DesiredObjectType(str(row["object_type"])),
        object_name=str(row["object_name"]),
        normalized_fingerprint=str(row["normalized_fingerprint"]),
        normalized_query=None if row["normalized_query"] is None else str(row["normalized_query"]),
        recorded_at=str(row["recorded_at"]),
    )


def _adapter_key(key: ObjectKey) -> AdapterMetadataObjectKey:
    return AdapterMetadataObjectKey(
        database=key.database,
        object_type=str(key.object_type),
        name=key.name,
    )


def _adapter_mapping(mapping: PreparedObjectMapping) -> AdapterPreparedObjectMapping:
    return AdapterPreparedObjectMapping(
        logical_key=_adapter_key(mapping.logical_key),
        physical_name=mapping.physical_name,
        logical_model_name=mapping.logical_model_name,
    )


def _adapter_deployment(deployment: DeploymentRecord) -> AdapterDeploymentRecord:
    return AdapterDeploymentRecord(
        deployment_id=deployment.deployment_id,
        created_at=deployment.created_at,
        status=deployment.status,
        replay_lineage_mode=str(deployment.replay_lineage_mode),
        selected_root_keys=tuple(_adapter_key(key) for key in deployment.selected_root_keys),
        warning_codes=deployment.warning_codes,
        prepared_object_mappings=tuple(
            _adapter_mapping(mapping) for mapping in deployment.prepared_object_mappings
        ),
    )
