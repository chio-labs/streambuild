from streambuild.compiler.metadata_state.models import (
    DeploymentRecord,
    DeploymentRuntimeDetailRecord,
    DeploymentWatermarkRecord,
    ObjectStateRecord,
    PreparedObjectMapping,
    PublishEventRecord,
)
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
)
from streambuild.compiler.shared.models import ObjectKey


def build_metadata_records() -> tuple[
    tuple[ObjectStateRecord, ...],
    tuple[DeploymentRecord, ...],
    tuple[DeploymentWatermarkRecord, ...],
    tuple[DeploymentRuntimeDetailRecord, ...],
    tuple[PublishEventRecord, ...],
]:
    root_key: ObjectKey = ObjectKey(
        database=None, object_type=DESIRED_OBJECT_TYPE_TABLE, name="raw__orders"
    )
    transform_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_TABLE,
        name="tbl__orders_enriched",
    )
    mv_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
        name="mv__orders_enriched",
    )
    object_states: tuple[ObjectStateRecord, ...] = (
        ObjectStateRecord(
            deployment_id="20260408T120000Z_ab12cd",
            key=transform_key,
            normalized_fingerprint="fingerprint_transform",
            normalized_query="SELECT * FROM raw__orders",
            recorded_at="2026-04-08T12:00:00Z",
        ),
        ObjectStateRecord(
            deployment_id="20260408T120000Z_ab12cd",
            key=mv_key,
            normalized_fingerprint="fingerprint_mv",
            normalized_query="SELECT * FROM raw__orders",
            recorded_at="2026-04-08T12:00:01Z",
        ),
    )
    deployments: tuple[DeploymentRecord, ...] = (
        DeploymentRecord(
            deployment_id="20260408T130000Z_cd34ef",
            created_at="2026-04-08T13:00:00Z",
            status="backfilling",
            replay_lineage_mode="offsets",
            selected_root_keys=(transform_key, root_key),
            warning_codes=("z_warning", "a_warning"),
            prepared_object_mappings=(
                PreparedObjectMapping(
                    logical_key=mv_key,
                    physical_name="mv__orders_enriched__20260408T130000Z_cd34ef",
                ),
                PreparedObjectMapping(
                    logical_key=transform_key,
                    physical_name="tbl__orders_enriched__20260408T130000Z_cd34ef",
                ),
            ),
        ),
        DeploymentRecord(
            deployment_id="20260408T120000Z_ab12cd",
            created_at="2026-04-08T12:00:00Z",
            status="published",
            replay_lineage_mode="timestamp",
            selected_root_keys=(root_key,),
            warning_codes=(),
            prepared_object_mappings=(),
        ),
    )
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...] = (
        DeploymentWatermarkRecord(
            deployment_id="20260408T130000Z_cd34ef",
            root_key=transform_key,
            anchor_key=root_key,
            boundary_key="partition:1",
            cutoff_value="54321",
        ),
        DeploymentWatermarkRecord(
            deployment_id="20260408T130000Z_cd34ef",
            root_key=transform_key,
            anchor_key=root_key,
            boundary_key="partition:0",
            cutoff_value="12345",
        ),
    )
    deployment_runtime_details: tuple[DeploymentRuntimeDetailRecord, ...] = (
        DeploymentRuntimeDetailRecord(
            deployment_id="20260408T130000Z_cd34ef",
            root_key=transform_key,
            state_kind="active_view_present",
            replay_strategy="bounded_replay",
            active_deployment_id="20260408T120000Z_ab12cd",
            anchor_key=root_key,
            anchor_physical_name="raw__orders__20260408T130000Z_cd34ef",
            execution_mode="seeded_bounded_rebuild",
            configured_backfill_mode="bounded",
            execution_lookback_seconds=604800,
            live_target_names=("tbl__orders_enriched",),
        ),
    )
    publish_events: tuple[PublishEventRecord, ...] = (
        PublishEventRecord(
            deployment_id="20260408T120000Z_ab12cd",
            published_at="2026-04-08T12:30:00Z",
            logical_view_names=("tbl__orders_enriched",),
        ),
    )
    return (
        object_states,
        deployments,
        deployment_watermarks,
        deployment_runtime_details,
        publish_events,
    )
