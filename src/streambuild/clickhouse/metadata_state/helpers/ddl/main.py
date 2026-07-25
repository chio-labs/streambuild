"""Build ClickHouse metadata-state DDL statements."""

from streambuild.clickhouse.metadata_state.constants import (
    METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_OBJECT_STATE_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
)
from streambuild.clickhouse.metadata_state.helpers.ddl.helpers.runtime_details import (
    render_create_deployment_runtime_details_table_ddl,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement


def render_metadata_state_statements(database: str) -> tuple[RenderedClickHouseStatement, ...]:
    """Render metadata-state DDL statements for ClickHouse persistence."""

    return (
        RenderedClickHouseStatement(sql=_render_create_object_state_table_ddl(database)),
        RenderedClickHouseStatement(sql=_render_create_deployments_table_ddl(database)),
        RenderedClickHouseStatement(sql=_render_create_deployment_watermarks_table_ddl(database)),
        RenderedClickHouseStatement(
            sql=render_create_deployment_runtime_details_table_ddl(database)
        ),
        RenderedClickHouseStatement(sql=_render_create_publish_history_table_ddl(database)),
    )


def _render_create_object_state_table_ddl(database: str) -> str:
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


def _render_create_deployments_table_ddl(database: str) -> str:
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


def _render_create_deployment_watermarks_table_ddl(database: str) -> str:
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


def _render_create_publish_history_table_ddl(database: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME} (\n"
        "    deployment_id String,\n"
        "    published_at DateTime64(3, 'UTC'),\n"
        "    logical_view_names_json String\n"
        ") ENGINE = ReplacingMergeTree(published_at)\n"
        "ORDER BY (deployment_id, published_at)"
    )
