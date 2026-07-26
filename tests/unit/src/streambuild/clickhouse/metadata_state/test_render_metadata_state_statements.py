import pytest

from streambuild.clickhouse.metadata_state._helpers.ddl.main import render_metadata_state_statements
from streambuild.clickhouse.metadata_state._helpers.statements.main import (
    build_metadata_state_insert_statements,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement
from tests.unit.src.streambuild.clickhouse.metadata_state._test_types import (
    MetadataStateInsertStatementTestCase,
    RenderMetadataStateDdlTestCase,
)
from tests.unit.src.streambuild.clickhouse.metadata_state.helpers import build_metadata_records

DDL_TEST_CASES: list[RenderMetadataStateDdlTestCase] = [
    RenderMetadataStateDdlTestCase(
        description="renders object-state metadata table ddl",
        expected_table_name="streambuild_object_state_snapshots",
        expected_fragments=(
            "CREATE TABLE IF NOT EXISTS metadata.streambuild_object_state_snapshots",
            "deployment_id String",
            "normalized_fingerprint String",
            "ENGINE = ReplacingMergeTree(recorded_at)",
        ),
    ),
    RenderMetadataStateDdlTestCase(
        description="renders deployments metadata table ddl",
        expected_table_name="streambuild_deployments",
        expected_fragments=(
            "CREATE TABLE IF NOT EXISTS metadata.streambuild_deployments",
            "prepared_object_mappings_json String",
            "ORDER BY (deployment_id)",
        ),
    ),
    RenderMetadataStateDdlTestCase(
        description="renders deployment-watermarks metadata table ddl",
        expected_table_name="streambuild_deployment_watermarks",
        expected_fragments=(
            "CREATE TABLE IF NOT EXISTS metadata.streambuild_deployment_watermarks",
            "boundary_key String",
            "cutoff_value String",
        ),
    ),
    RenderMetadataStateDdlTestCase(
        description="renders deployment-runtime-details metadata table ddl",
        expected_table_name="streambuild_deployment_runtime_details",
        expected_fragments=(
            "CREATE TABLE IF NOT EXISTS metadata.streambuild_deployment_runtime_details",
            "state_kind String",
            "live_target_names_json String",
        ),
    ),
    RenderMetadataStateDdlTestCase(
        description="renders publish-history metadata table ddl",
        expected_table_name="streambuild_publish_history",
        expected_fragments=(
            "CREATE TABLE IF NOT EXISTS metadata.streambuild_publish_history",
            "published_at DateTime64(3, 'UTC')",
            "logical_view_names_json String",
        ),
    ),
]

INSERT_STATEMENT_TEST_CASES: list[MetadataStateInsertStatementTestCase] = [
    MetadataStateInsertStatementTestCase(
        description="builds object-state insert statement rows",
        expected_sql_fragment="INSERT INTO metadata.streambuild_object_state_snapshots",
        expected_row_count=1,
        expected_first_row_fragments=(
            ("deployment_id", "20260408T130000Z_ab12cd"),
            ("object_name", "tbl__orders_enriched"),
            ("normalized_fingerprint", "fingerprint_transform"),
        ),
    ),
    MetadataStateInsertStatementTestCase(
        description="builds deployments insert statement rows",
        expected_sql_fragment="INSERT INTO metadata.streambuild_deployments",
        expected_row_count=1,
        expected_first_row_fragments=(
            ("deployment_id", "20260408T130000Z_ab12cd"),
            ("status", "backfilling"),
        ),
    ),
    MetadataStateInsertStatementTestCase(
        description="builds deployment-watermarks insert statement rows",
        expected_sql_fragment="INSERT INTO metadata.streambuild_deployment_watermarks",
        expected_row_count=1,
        expected_first_row_fragments=(
            ("boundary_key", "partition:0"),
            ("cutoff_value", "12345"),
        ),
    ),
    MetadataStateInsertStatementTestCase(
        description="builds deployment-runtime-details insert statement rows",
        expected_sql_fragment="INSERT INTO metadata.streambuild_deployment_runtime_details",
        expected_row_count=1,
        expected_first_row_fragments=(
            ("state_kind", "active_view_present"),
            ("replay_strategy", "bounded_replay"),
            ("live_target_names_json", '["tbl__orders_enriched"]'),
        ),
    ),
    MetadataStateInsertStatementTestCase(
        description="builds publish-history insert statement rows",
        expected_sql_fragment="INSERT INTO metadata.streambuild_publish_history",
        expected_row_count=1,
        expected_first_row_fragments=(
            ("deployment_id", "20260408T130000Z_ab12cd"),
            ("logical_view_names_json", '["tbl__orders_enriched"]'),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DDL_TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_metadata_database_when_rendering_then_it_returns_expected_metadata_ddl(
    test_case: RenderMetadataStateDdlTestCase,
) -> None:
    rendered_statements: tuple[RenderedClickHouseStatement, ...] = render_metadata_state_statements(
        "metadata"
    )

    matching_statement: RenderedClickHouseStatement = next(
        statement
        for statement in rendered_statements
        if test_case.expected_table_name in statement.sql
    )

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in matching_statement.sql


@pytest.mark.parametrize(
    "test_case",
    INSERT_STATEMENT_TEST_CASES,
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
        "metadata",
        object_states,
        deployments,
        deployment_watermarks,
        deployment_runtime_details,
        publish_events,
    )
    statement: RenderedClickHouseStatement = next(
        statement for statement in statements if test_case.expected_sql_fragment in statement.sql
    )

    assert test_case.expected_sql_fragment in statement.sql
    assert len(statement.rows) == test_case.expected_row_count
    first_row: dict[str, object] = statement.rows[0]
    for key, expected_value in test_case.expected_first_row_fragments:
        assert first_row[key] == expected_value
