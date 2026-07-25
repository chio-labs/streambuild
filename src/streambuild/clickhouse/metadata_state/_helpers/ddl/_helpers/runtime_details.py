"""DDL builder for deployment runtime-details metadata."""

from streambuild.clickhouse.metadata_state.constants import (
    METADATA_DEPLOYMENT_RUNTIME_DETAILS_TABLE_NAME,
)


def render_create_deployment_runtime_details_table_ddl(database: str) -> str:
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
