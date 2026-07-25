"""Build ClickHouse metadata-state insert statements."""

from streambuild.clickhouse.metadata_state.constants import (
    METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME,
    METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_OBJECT_STATE_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
)
from streambuild.clickhouse.metadata_state.helpers.statements.helpers.rows import (
    build_deployment_row,
    build_deployment_runtime_detail_row,
    build_deployment_watermark_row,
    build_object_state_row,
    build_publish_event_row,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement
from streambuild.compiler.metadata_state.models import (
    DeploymentRecord,
    DeploymentRuntimeDetailRecord,
    DeploymentWatermarkRecord,
    ObjectStateRecord,
    PublishEventRecord,
)


def build_metadata_state_insert_statements(
    database: str,
    object_states: tuple[ObjectStateRecord, ...],
    deployments: tuple[DeploymentRecord, ...],
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...],
    deployment_runtime_details: tuple[DeploymentRuntimeDetailRecord, ...],
    publish_events: tuple[PublishEventRecord, ...],
) -> tuple[RenderedClickHouseStatement, ...]:
    """Build ClickHouse insert statements for metadata-state records."""

    return (
        RenderedClickHouseStatement(
            sql=(
                f"INSERT INTO {database}.{METADATA_OBJECT_STATE_TABLE_NAME} "
                "(deployment_id, database_name, object_type, object_name, normalized_fingerprint, "
                "normalized_query, recorded_at) VALUES"
            ),
            rows=tuple(build_object_state_row(record) for record in object_states),
        ),
        RenderedClickHouseStatement(
            sql=(
                f"INSERT INTO {database}.{METADATA_DEPLOYMENTS_TABLE_NAME} "
                "(deployment_id, created_at, status, replay_lineage_mode, "
                "selected_root_keys_json, warning_codes_json, prepared_object_mappings_json) VALUES"
            ),
            rows=tuple(build_deployment_row(record) for record in deployments),
        ),
        RenderedClickHouseStatement(
            sql=(
                f"INSERT INTO {database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} "
                "(deployment_id, root_database_name, root_object_type, root_object_name, "
                "anchor_database_name, anchor_object_type, anchor_object_name, boundary_key, "
                "cutoff_value) VALUES"
            ),
            rows=tuple(build_deployment_watermark_row(record) for record in deployment_watermarks),
        ),
        RenderedClickHouseStatement(
            sql=(
                f"INSERT INTO {database}.{METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME} "
                "(deployment_id, root_database_name, root_object_type, root_object_name, "
                "state_kind, replay_strategy, active_deployment_id, anchor_database_name, "
                "anchor_object_type, anchor_object_name, anchor_physical_name, execution_mode, "
                "configured_backfill_mode, "
                "execution_lookback_seconds, live_target_names_json) VALUES"
            ),
            rows=tuple(
                build_deployment_runtime_detail_row(record) for record in deployment_runtime_details
            ),
        ),
        RenderedClickHouseStatement(
            sql=(
                f"INSERT INTO {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME} "
                "(deployment_id, published_at, logical_view_names_json) VALUES"
            ),
            rows=tuple(build_publish_event_row(record) for record in publish_events),
        ),
    )
