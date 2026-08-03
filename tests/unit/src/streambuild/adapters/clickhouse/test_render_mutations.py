from typing import cast

import pytest

from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterIdentity,
    AdapterMetadataState,
    AdapterOwnershipRecord,
    AdapterRelationCleanupRequest,
    AdapterStableBinding,
    AdapterStableBindingRemoval,
    CatalogColumn,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapter.types import AdapterOwningMode
from streambuild.adapters.clickhouse.classes.clickhouse_connection import ClickHouseConnection
from streambuild.adapters.clickhouse.types import RawClickHouseClient
from streambuild.compiler.planner.main.build_adapter_metadata_state import (
    build_adapter_metadata_state,
)
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    RenderLifecycleMutationSqlTestCase,
    RenderMetadataMutationSqlTestCase,
    RenderOwnershipMutationSqlTestCase,
)
from tests.unit.src.streambuild.adapters.clickhouse.helpers import (
    FakeRawClickHouseQueryResult,
    GuardedRenderingClickHouseConnection,
    StubRawClickHouseClient,
    build_metadata_state,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderMetadataMutationSqlTestCase(
            description="renders database and metadata mutations as exact executable SQL",
            expected_database_sql="CREATE DATABASE IF NOT EXISTS metadata;",
            expected_migration_statement_count=11,
            expected_migration_last_sql=(
                "INSERT INTO metadata._streambuild_schema_versions "
                "(version, applied_at) SELECT 1, now64(3, 'UTC') WHERE NOT EXISTS ("
                "SELECT 1 FROM metadata._streambuild_schema_versions WHERE version = 1);"
            ),
            expected_persistence_first_sql=(
                "INSERT INTO metadata._streambuild_virtual_object_state "
                "(state_id, observation_id, state_kind, deployment_id, logical_database_name, "
                "logical_object_type, logical_object_name, physical_database_name, "
                "physical_relation_name, logical_model_database, logical_model_name, "
                "is_selected_root, object_fingerprint, canonical_query, observed_at) VALUES\n"
                "('20260408T130000Z_ab12cd', "
                "'622c1dd60e3a5b7e56eae621b143b0756a7fdb685c421d446873718ef43e979e', "
                "'deployment', '20260408T130000Z_ab12cd', NULL, "
                "'table', 'tbl__orders_enriched', NULL, "
                "'tbl__orders_enriched__20260408T130000Z_ab12cd', NULL, 'orders_enriched', false, "
                "'fingerprint_transform', 'SELECT * FROM raw__orders', "
                "'2026-04-08T13:00:00Z');"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_metadata_requests_when_rendering_mutations_then_sql_is_exact_and_terminated(
    test_case: RenderMetadataMutationSqlTestCase,
) -> None:
    raw_client: StubRawClickHouseClient = StubRawClickHouseClient(
        FakeRawClickHouseQueryResult(column_names=[], result_rows=[])
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))
    state: AdapterMetadataState = build_adapter_metadata_state(build_metadata_state())

    migration_sql: tuple[str, ...] = connection.render_migrate_metadata_state("metadata")
    persistence_sql: tuple[str, ...] = connection.render_persist_metadata_state(
        database="metadata",
        state=state,
    )

    assert connection.render_ensure_database("metadata") == test_case.expected_database_sql
    assert len(migration_sql) == test_case.expected_migration_statement_count
    assert migration_sql[-1] == test_case.expected_migration_last_sql
    assert persistence_sql[0] == test_case.expected_persistence_first_sql
    assert all(statement.endswith(";") for statement in (*migration_sql, *persistence_sql))
    assert all(not statement.endswith(";;") for statement in (*migration_sql, *persistence_sql))


@pytest.mark.parametrize(
    "test_case",
    [
        RenderOwnershipMutationSqlTestCase(
            description="renders ownership claims and removals with embedded values",
            expected_record_sql=(
                "INSERT INTO metadata._streambuild_direct_replay_ranges "
                "(replay_set_id, target_database_name, logical_model_database, "
                "logical_model_name, range_present, driving_input_relation_name, "
                "replay_boundary_mode, partition_value, source_partition_column_name, "
                "source_position_column_name, source_timestamp_column_name, lower_value, "
                "upper_value, replay_cutoff_value, captured_at) VALUES\n"
                "('135e1e9bddf7b29d67a4c6b302feff36ba66fd38bc1047a0eaff320fe92c2736', "
                "'analytics', NULL, 'orders', false, NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
                "NULL, NULL, now64(3, 'UTC'));",
                "INSERT INTO metadata._streambuild_direct_target_events "
                "(event_id, workflow_id, event_kind, database_name, relation_name, resource_kind, "
                "logical_model_database, logical_model_name, tool_version, replay_set_id, "
                "recorded_at) VALUES\n"
                "('363938ccd6ef16f7a914b16f17a94cc3ab1fdab4587c17d99e7526b18c0f7616', "
                "'5e80686ff7e81de5d62f9cd04d36092a6425b0e10152281e841bd50d12d0e747', 'claimed', "
                "'analytics', 'tbl__orders', 'table', NULL, 'orders', '1.2.3', "
                "'135e1e9bddf7b29d67a4c6b302feff36ba66fd38bc1047a0eaff320fe92c2736', "
                "now64(3, 'UTC'));",
            ),
            expected_removal_sql=(
                "INSERT INTO metadata._streambuild_direct_target_events "
                "(event_id, workflow_id, event_kind, database_name, relation_name, resource_kind, "
                "logical_model_database, logical_model_name, tool_version, replay_set_id, "
                "recorded_at) SELECT hex(SHA256(concat('release:', current_state.1))), "
                "'61096b4b883768c657cc55a6c6fedce01a54fd7f581bd4278997817806a3d141', 'released', "
                "database_name, relation_name, current_state.3, current_state.4, current_state.5, "
                "current_state.6, NULL, now64(3, 'UTC') FROM (SELECT database_name, "
                "relation_name, argMax(tuple(event_id, event_kind, resource_kind, "
                "logical_model_database, logical_model_name, tool_version), tuple(recorded_at, "
                "event_id)) AS current_state FROM metadata._streambuild_direct_target_events "
                "WHERE database_name = 'analytics' AND relation_name IN ('tbl__orders', "
                "'mv__orders') GROUP BY database_name, relation_name) WHERE current_state.2 != "
                "'released';"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ownership_requests_when_rendering_mutations_then_sql_is_exact(
    test_case: RenderOwnershipMutationSqlTestCase,
) -> None:
    raw_client: StubRawClickHouseClient = StubRawClickHouseClient(
        FakeRawClickHouseQueryResult(column_names=[], result_rows=[])
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))
    record: AdapterOwnershipRecord = AdapterOwnershipRecord(
        database_name="analytics",
        relation_name="tbl__orders",
        resource_kind="table",
        logical_model_name="orders",
        owning_mode=AdapterOwningMode.DIRECT,
        tool_version="1.2.3",
    )

    record_sql: tuple[str, ...] = connection.render_record_target_ownership(
        database="metadata",
        records=(record,),
    )
    removal_sql: tuple[str, ...] = connection.render_remove_target_ownership(
        database="metadata",
        target_database="analytics",
        relation_names=("tbl__orders", "mv__orders"),
    )

    assert record_sql == test_case.expected_record_sql
    assert removal_sql == (test_case.expected_removal_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderLifecycleMutationSqlTestCase(
            description="renders binding and kind-aware cleanup statements in request order",
            expected_binding_sql=(
                "CREATE OR REPLACE VIEW analytics.tbl__orders AS\n"
                "SELECT * FROM analytics.tbl__orders__candidate;",
                "DROP VIEW IF EXISTS analytics.tbl__obsolete SYNC;",
            ),
            expected_cleanup_sql=(
                "DROP TABLE IF EXISTS analytics.tbl__orders__old SYNC;",
                "DROP VIEW IF EXISTS analytics.view__orders__old SYNC;",
            ),
            expected_inspection_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_lifecycle_requests_when_rendering_mutations_then_guards_and_sql_are_exact(
    test_case: RenderLifecycleMutationSqlTestCase,
) -> None:
    catalog: CatalogSnapshot = CatalogSnapshot(
        identity=CatalogIdentity(
            adapter=AdapterIdentity(name="clickhouse"),
            database="analytics",
        ),
        warehouse_timezone="UTC",
        relations=(
            CatalogRelation(
                name="tbl__orders__old",
                engine="MergeTree",
                columns=(CatalogColumn(name="order_id", type="String"),),
            ),
            CatalogRelation(
                name="view__orders__old",
                engine="View",
                columns=(CatalogColumn(name="order_id", type="String"),),
            ),
        ),
    )
    connection: GuardedRenderingClickHouseConnection = GuardedRenderingClickHouseConnection(
        catalog=catalog,
        managed_table_state=InspectedManagedTableState(active_bindings=(), physical_candidates=()),
    )
    binding_sql: tuple[str, ...] = connection.render_replace_stable_bindings(
        AdapterBindingReplacementRequest(
            bindings=(
                AdapterStableBinding(
                    database="analytics",
                    logical_name="tbl__orders",
                    physical_name="tbl__orders__candidate",
                ),
            ),
            removals=(
                AdapterStableBindingRemoval(
                    database="analytics",
                    logical_name="tbl__obsolete",
                ),
            ),
        )
    )
    cleanup_sql: tuple[str, ...] = connection.render_cleanup_relations(
        AdapterRelationCleanupRequest(
            database="analytics",
            relation_names=("tbl__orders__old", "view__orders__old"),
        )
    )

    assert binding_sql == test_case.expected_binding_sql
    assert cleanup_sql == test_case.expected_cleanup_sql
    assert connection.inspection_count == test_case.expected_inspection_count
