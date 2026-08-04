from dataclasses import replace

import pytest

from streambuild.adapter.models import (
    AdapterInvocationRecord,
    AdapterMetadataState,
    AdapterNodeResultRecord,
)
from streambuild.adapters.clickhouse._helpers.metadata import (
    build_clickhouse_metadata_insert_statements,
    render_clickhouse_metadata_migration_statements,
)
from streambuild.adapters.clickhouse.models import ClickHouseMetadataStatement
from streambuild.compiler.planner.main.build_adapter_metadata_state import (
    build_adapter_metadata_state,
)
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    MetadataStateInsertStatementTestCase,
    RenderMetadataStateDdlTestCase,
    TerminalObservationInsertTestCase,
)
from tests.unit.src.streambuild.adapters.clickhouse.helpers import build_metadata_state


@pytest.mark.parametrize(
    "test_case",
    [
        RenderMetadataStateDdlTestCase(
            description="renders object-state metadata table ddl",
            statement_index=0,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_virtual_object_state (\n"
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
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders deployments metadata table ddl",
            statement_index=1,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_virtual_deployments (\n"
                "    deployment_id String,\n"
                "    workflow_fingerprint String,\n"
                "    replay_lineage_mode String,\n"
                "    boundary_time DateTime64(3, 'UTC'),\n"
                "    created_at DateTime64(3, 'UTC'),\n"
                "    tool_version String\n"
                ") ENGINE = MergeTree\n"
                "ORDER BY (deployment_id)"
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders deployment-watermarks metadata table ddl",
            statement_index=2,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_virtual_replay_boundaries (\n"
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
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders publish-history metadata table ddl",
            statement_index=3,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_virtual_publications (\n"
                "    publication_id String,\n"
                "    deployment_id String,\n"
                "    logical_database_name String,\n"
                "    logical_view_name String,\n"
                "    physical_database_name String,\n"
                "    physical_relation_name String,\n"
                "    published_at DateTime64(3, 'UTC')\n"
                ") ENGINE = MergeTree\n"
                "ORDER BY (publication_id, logical_database_name, logical_view_name)"
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders direct replay ranges metadata table ddl",
            statement_index=4,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_direct_replay_ranges (\n"
                "    capture_id String,\n"
                "    replay_set_id String,\n"
                "    workflow_id String,\n"
                "    checkpoint_sequence UInt8,\n"
                "    target_database_name String,\n"
                "    logical_model_database Nullable(String),\n"
                "    logical_model_name String,\n"
                "    range_present Bool,\n"
                "    driving_input_relation_name Nullable(String),\n"
                "    replay_boundary_mode Nullable(String),\n"
                "    partition_value Nullable(String),\n"
                "    source_partition_column_name Nullable(String),\n"
                "    source_position_column_name Nullable(String),\n"
                "    source_timestamp_column_name Nullable(String),\n"
                "    lower_value Nullable(String),\n"
                "    upper_value Nullable(String),\n"
                "    replay_cutoff_value Nullable(String),\n"
                "    captured_at DateTime64(9, 'UTC')\n"
                ") ENGINE = MergeTree\n"
                "ORDER BY (capture_id, replay_set_id, range_present)"
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders direct replay checkpoints metadata table ddl",
            statement_index=5,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_direct_replay_checkpoints (\n"
                "    checkpoint_id String,\n"
                "    workflow_id String,\n"
                "    target_database_name String,\n"
                "    logical_model_name String,\n"
                "    capture_id String,\n"
                "    replay_set_id String,\n"
                "    checkpoint_sequence UInt8,\n"
                "    recorded_at DateTime64(9, 'UTC')\n"
                ") ENGINE = MergeTree\n"
                "ORDER BY (checkpoint_id, checkpoint_sequence, recorded_at, capture_id)"
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders successful direct fingerprints metadata table ddl",
            statement_index=6,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_direct_fingerprints (\n"
                "    fingerprint_id String, logical_model_identity String, physical_database "
                "String,\n"
                "    physical_relation String, resource_kind String, definition_sql String,\n"
                "    definition_hash String, rendered_definition_hash String,\n"
                "    schema_fingerprint String, workflow_id String, tool_version String,\n"
                "    succeeded_at DateTime64(3, 'UTC')\n"
                ") ENGINE = MergeTree ORDER BY (logical_model_identity, succeeded_at, "
                "fingerprint_id)"
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders invocation history table ddl",
            statement_index=7,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_invocations (\n"
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
            ),
        ),
        RenderMetadataStateDdlTestCase(
            description="renders node result history table ddl",
            statement_index=8,
            expected_sql=(
                "CREATE TABLE IF NOT EXISTS metadata._streambuild_node_results (\n"
                "    result_id String,\n"
                "    invocation_id String,\n"
                "    node_kind LowCardinality(String),\n"
                "    node_identity String,\n"
                "    definition_fingerprint String,\n"
                "    target_identity String,\n"
                "    status LowCardinality(String),\n"
                "    severity Nullable(String),\n"
                "    failure_count UInt64,\n"
                "    completed_at DateTime64(3, 'UTC'),\n"
                "    payload_json String,\n"
                "    error_message Nullable(String)\n"
                ") ENGINE = MergeTree\n"
                "ORDER BY (node_kind, node_identity, completed_at, result_id)"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_metadata_database_when_rendering_then_it_returns_expected_metadata_ddl(
    test_case: RenderMetadataStateDdlTestCase,
) -> None:
    rendered_statements: tuple[str, ...] = render_clickhouse_metadata_migration_statements(
        "metadata"
    )

    matching_statement: str = rendered_statements[test_case.statement_index]

    assert matching_statement == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        MetadataStateInsertStatementTestCase(
            description="builds object-state insert statement rows",
            statement_index=0,
            expected_sql=(
                "INSERT INTO metadata._streambuild_virtual_object_state "
                "(state_id, observation_id, state_kind, deployment_id, logical_database_name, "
                "logical_object_type, logical_object_name, physical_database_name, "
                "physical_relation_name, logical_model_database, logical_model_name, "
                "is_selected_root, object_fingerprint, canonical_query, observed_at) VALUES"
            ),
            expected_row={
                "state_id": "20260408T130000Z_ab12cd",
                "observation_id": (
                    "622c1dd60e3a5b7e56eae621b143b0756a7fdb685c421d446873718ef43e979e"
                ),
                "state_kind": "deployment",
                "deployment_id": "20260408T130000Z_ab12cd",
                "logical_database_name": None,
                "logical_object_type": "table",
                "logical_object_name": "tbl__orders_enriched",
                "physical_database_name": None,
                "physical_relation_name": "tbl__orders_enriched__20260408T130000Z_ab12cd",
                "logical_model_database": None,
                "logical_model_name": "orders_enriched",
                "is_selected_root": False,
                "object_fingerprint": "fingerprint_transform",
                "canonical_query": "SELECT * FROM raw__orders",
                "observed_at": "2026-04-08T13:00:00Z",
            },
        ),
        MetadataStateInsertStatementTestCase(
            description="builds deployments insert statement rows",
            statement_index=1,
            expected_sql=(
                "INSERT INTO metadata._streambuild_virtual_deployments "
                "(deployment_id, workflow_fingerprint, replay_lineage_mode, boundary_time, "
                "created_at, tool_version) VALUES"
            ),
            expected_row={
                "deployment_id": "20260408T130000Z_ab12cd",
                "workflow_fingerprint": "workflow-fingerprint",
                "replay_lineage_mode": "offsets",
                "boundary_time": "2026-04-08T13:00:05Z",
                "created_at": "2026-04-08T13:00:00Z",
                "tool_version": "1.2.3",
            },
        ),
        MetadataStateInsertStatementTestCase(
            description="builds deployment-watermarks insert statement rows",
            statement_index=2,
            expected_sql=(
                "INSERT INTO metadata._streambuild_virtual_replay_boundaries "
                "(deployment_id, root_database_name, root_object_type, root_object_name, "
                "anchor_database_name, anchor_object_type, anchor_object_name, boundary_kind, "
                "value_kind, partition_value, lower_value, cutoff_value, cutoff_inclusive, "
                "captured_at) VALUES"
            ),
            expected_row={
                "deployment_id": "20260408T130000Z_ab12cd",
                "root_database_name": None,
                "root_object_type": "table",
                "root_object_name": "tbl__orders_enriched",
                "anchor_database_name": None,
                "anchor_object_type": "table",
                "anchor_object_name": "raw__orders",
                "boundary_kind": "offsets",
                "value_kind": "integer",
                "partition_value": "0",
                "lower_value": None,
                "cutoff_value": "12345",
                "cutoff_inclusive": True,
                "captured_at": "1970-01-01 00:00:00.000",
            },
        ),
        MetadataStateInsertStatementTestCase(
            description="builds publish-history insert statement rows",
            statement_index=3,
            expected_sql=(
                "INSERT INTO metadata._streambuild_virtual_publications "
                "(publication_id, deployment_id, logical_database_name, logical_view_name, "
                "physical_database_name, physical_relation_name, published_at) VALUES"
            ),
            expected_row={
                "publication_id": (
                    "62c4eb02c52a827ca9c617edd681fa320d3090c943a2937b68cd52073afe8d45"
                ),
                "deployment_id": "20260408T130000Z_ab12cd",
                "logical_database_name": "analytics",
                "logical_view_name": "tbl__orders_enriched",
                "physical_database_name": "analytics",
                "physical_relation_name": ("tbl__orders_enriched__20260408T130000Z_ab12cd"),
                "published_at": "2026-04-08T13:30:00Z",
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_metadata_records_when_building_insert_statement_then_it_returns_expected_rows(
    test_case: MetadataStateInsertStatementTestCase,
) -> None:
    statements: tuple[ClickHouseMetadataStatement, ...] = (
        build_clickhouse_metadata_insert_statements(
            database="metadata",
            state=build_adapter_metadata_state(build_metadata_state()),
        )
    )
    statement: ClickHouseMetadataStatement = statements[test_case.statement_index]

    assert statement.sql == test_case.expected_sql
    assert statement.rows == (test_case.expected_row,)


@pytest.mark.parametrize(
    "test_case",
    [
        TerminalObservationInsertTestCase(
            description="builds structured terminal observation rows",
            expected_invocation_id="inv-1",
            expected_result_id="result-1",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_terminal_observations_when_building_inserts_then_rows_are_structured(
    test_case: TerminalObservationInsertTestCase,
) -> None:
    invocation: AdapterInvocationRecord = AdapterInvocationRecord(
        invocation_id=test_case.expected_invocation_id,
        project_identity="/projects/orders",
        target_identity="analytics",
        command="audit",
        mode=None,
        outcome="failed",
        exit_code=1,
        materialized_outcome=None,
        deployment_id=None,
        workflow_id=None,
        selected_node_count=1,
        started_at="2026-08-02 12:00:00.000",
        completed_at="2026-08-02 12:00:01.000",
        duration_ms=1000,
        error_message=None,
        summary_json='{"error_failure_count":1}',
        tool_version="1.2.3",
    )
    node_result: AdapterNodeResultRecord = AdapterNodeResultRecord(
        result_id=test_case.expected_result_id,
        invocation_id=test_case.expected_invocation_id,
        node_kind="audit",
        node_identity="audits/orders.sql:1",
        definition_fingerprint="fingerprint",
        target_identity="analytics",
        status="failed",
        severity="error",
        failure_count=2,
        completed_at="2026-08-02 12:00:01.000",
        payload_json='{"sample_rows":[[1],[2]]}',
        error_message=None,
    )
    state: AdapterMetadataState = replace(
        build_adapter_metadata_state(build_metadata_state()),
        invocations=(invocation,),
        node_results=(node_result,),
    )

    statements: tuple[ClickHouseMetadataStatement, ...] = (
        build_clickhouse_metadata_insert_statements(database="metadata", state=state)
    )

    assert statements[4].rows == (invocation.__dict__,)
    assert statements[5].rows == (node_result.__dict__,)
    assert statements[4].rows[0]["invocation_id"] == test_case.expected_invocation_id
    assert statements[5].rows[0]["result_id"] == test_case.expected_result_id
