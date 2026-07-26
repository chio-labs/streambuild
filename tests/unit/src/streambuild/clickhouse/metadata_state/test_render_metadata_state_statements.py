import pytest

from streambuild.clickhouse.metadata_state.main.build_metadata_state_insert_statements import (
    build_metadata_state_insert_statements,
)
from streambuild.clickhouse.metadata_state.main.render_metadata_state_statements import (
    render_metadata_state_statements,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement
from tests.unit.src.streambuild.clickhouse.metadata_state._test_types import (
    MetadataStateInsertStatementTestCase,
    RenderMetadataStateDdlTestCase,
)
from tests.unit.src.streambuild.clickhouse.metadata_state.helpers import build_metadata_records


@pytest.mark.parametrize(
    "test_case",
    [
        RenderMetadataStateDdlTestCase(
            description="renders object-state metadata table ddl",
            statement_index=0,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata.streambuild_object_state_snapshots (\n"
                "    deployment_id String,\n"
                "    database_name Nullable(String),\n"
                "    object_type String,\n"
                "    object_name String,\n"
                "    normalized_fingerprint String,\n"
                "    normalized_query Nullable(String),\n"
                "    recorded_at DateTime64(3, 'UTC')\n"
                ") ENGINE = ReplacingMergeTree(recorded_at)\n"
                "ORDER BY (deployment_id, object_type, object_name)"
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders deployments metadata table ddl",
            statement_index=1,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata.streambuild_deployments (\n"
                "    deployment_id String,\n"
                "    created_at DateTime64(3, 'UTC'),\n"
                "    status String,\n"
                "    replay_lineage_mode String,\n"
                "    selected_root_keys_json String,\n"
                "    warning_codes_json String,\n"
                "    prepared_object_mappings_json String\n"
                ") ENGINE = ReplacingMergeTree(created_at)\n"
                "ORDER BY (deployment_id)"
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders deployment-watermarks metadata table ddl",
            statement_index=2,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata.streambuild_deployment_watermarks (\n"
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
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders deployment-runtime-details metadata table ddl",
            statement_index=3,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata.streambuild_deployment_runtime_details (\n"
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
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders publish-history metadata table ddl",
            statement_index=4,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata.streambuild_publish_history (\n"
                "    deployment_id String,\n"
                "    published_at DateTime64(3, 'UTC'),\n"
                "    logical_view_names_json String\n"
                ") ENGINE = ReplacingMergeTree(published_at)\n"
                "ORDER BY (deployment_id, published_at)"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_metadata_database_when_rendering_then_it_returns_expected_metadata_ddl(
    test_case: RenderMetadataStateDdlTestCase,
) -> None:
    rendered_statements: tuple[RenderedClickHouseStatement, ...] = render_metadata_state_statements(
        "metadata"
    )

    matching_statement: RenderedClickHouseStatement = rendered_statements[test_case.statement_index]

    assert matching_statement.sql == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        MetadataStateInsertStatementTestCase(
            description="builds object-state insert statement rows",
            statement_index=0,
            expected_sql=(
                "INSERT INTO metadata.streambuild_object_state_snapshots "
                "(deployment_id, database_name, object_type, object_name, "
                "normalized_fingerprint, normalized_query, recorded_at) VALUES"
            ),
            expected_row={
                "deployment_id": "20260408T130000Z_ab12cd",
                "database_name": None,
                "object_type": "table",
                "object_name": "tbl__orders_enriched",
                "normalized_fingerprint": "fingerprint_transform",
                "normalized_query": "SELECT * FROM raw__orders",
                "recorded_at": "2026-04-08T13:00:00Z",
            },
        ),
        MetadataStateInsertStatementTestCase(
            description="builds deployments insert statement rows",
            statement_index=1,
            expected_sql=(
                "INSERT INTO metadata.streambuild_deployments "
                "(deployment_id, created_at, status, replay_lineage_mode, "
                "selected_root_keys_json, warning_codes_json, "
                "prepared_object_mappings_json) VALUES"
            ),
            expected_row={
                "deployment_id": "20260408T130000Z_ab12cd",
                "created_at": "2026-04-08T13:00:00Z",
                "status": "backfilling",
                "replay_lineage_mode": "offsets",
                "selected_root_keys_json": (
                    '[{"database": null, "object_type": "table", "name": "raw__orders"}]'
                ),
                "warning_codes_json": '["mutable_ref_replay_not_guaranteed"]',
                "prepared_object_mappings_json": (
                    '[{"logical_key": {"database": null, "object_type": "table", '
                    '"name": "tbl__orders_enriched"}, "physical_name": '
                    '"tbl__orders_enriched__20260408T130000Z_ab12cd"}]'
                ),
            },
        ),
        MetadataStateInsertStatementTestCase(
            description="builds deployment-watermarks insert statement rows",
            statement_index=2,
            expected_sql=(
                "INSERT INTO metadata.streambuild_deployment_watermarks "
                "(deployment_id, root_database_name, root_object_type, root_object_name, "
                "anchor_database_name, anchor_object_type, anchor_object_name, boundary_key, "
                "cutoff_value) VALUES"
            ),
            expected_row={
                "deployment_id": "20260408T130000Z_ab12cd",
                "root_database_name": None,
                "root_object_type": "table",
                "root_object_name": "tbl__orders_enriched",
                "anchor_database_name": None,
                "anchor_object_type": "table",
                "anchor_object_name": "raw__orders",
                "boundary_key": "partition:0",
                "cutoff_value": "12345",
            },
        ),
        MetadataStateInsertStatementTestCase(
            description="builds deployment-runtime-details insert statement rows",
            statement_index=3,
            expected_sql=(
                "INSERT INTO metadata.streambuild_deployment_runtime_details "
                "(deployment_id, root_database_name, root_object_type, root_object_name, "
                "state_kind, replay_strategy, active_deployment_id, anchor_database_name, "
                "anchor_object_type, anchor_object_name, anchor_physical_name, execution_mode, "
                "configured_backfill_mode, execution_lookback_seconds, "
                "live_target_names_json) VALUES"
            ),
            expected_row={
                "deployment_id": "20260408T130000Z_ab12cd",
                "root_database_name": None,
                "root_object_type": "table",
                "root_object_name": "tbl__orders_enriched",
                "state_kind": "active_view_present",
                "replay_strategy": "bounded_replay",
                "active_deployment_id": "20260408T120000Z_zz99yy",
                "anchor_database_name": None,
                "anchor_object_type": "table",
                "anchor_object_name": "raw__orders",
                "anchor_physical_name": "raw__orders__20260408T130000Z_ab12cd",
                "execution_mode": "seeded_bounded_rebuild",
                "configured_backfill_mode": "bounded",
                "execution_lookback_seconds": 604800,
                "live_target_names_json": '["tbl__orders_enriched"]',
            },
        ),
        MetadataStateInsertStatementTestCase(
            description="builds publish-history insert statement rows",
            statement_index=4,
            expected_sql=(
                "INSERT INTO metadata.streambuild_publish_history "
                "(deployment_id, published_at, logical_view_names_json) VALUES"
            ),
            expected_row={
                "deployment_id": "20260408T130000Z_ab12cd",
                "published_at": "2026-04-08T13:30:00Z",
                "logical_view_names_json": '["tbl__orders_enriched"]',
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_metadata_records_when_building_insert_statement_then_it_returns_expected_rows(
    test_case: MetadataStateInsertStatementTestCase,
) -> None:
    (
        object_states,
        deployments,
        deployment_watermarks,
        deployment_runtime_details,
        publish_events,
    ) = build_metadata_records()
    statements: tuple[RenderedClickHouseStatement, ...] = build_metadata_state_insert_statements(
        database="metadata",
        object_states=object_states,
        deployments=deployments,
        deployment_watermarks=deployment_watermarks,
        deployment_runtime_details=deployment_runtime_details,
        publish_events=publish_events,
    )
    statement: RenderedClickHouseStatement = statements[test_case.statement_index]

    assert statement.sql == test_case.expected_sql
    assert statement.rows == (test_case.expected_row,)
