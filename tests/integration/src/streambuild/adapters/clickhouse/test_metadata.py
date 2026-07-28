from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Barrier

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterConnectionConfig,
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterOwnershipRecord,
)
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.executor.audit_backfill.main.load_audit_deployment import load_audit_deployment
from streambuild.executor.audit_backfill.models import LoadedAuditDeployment
from tests.integration.src.streambuild.adapters.clickhouse._test_types import (
    LegacyMetadataMigrationIntegrationTestCase,
    MetadataMigrationIntegrationTestCase,
    TargetOwnershipIntegrationTestCase,
)
from tests.integration.src.streambuild.adapters.clickhouse.helpers import (
    connect_clickhouse,
    integer_rows,
    ownership_summaries,
    run_metadata_migration,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        MetadataMigrationIntegrationTestCase(
            description="empty metadata state migrates repeatedly without duplicate versions",
            expected_table_names=(
                "streambuild_deployment_runtime_details",
                "streambuild_deployment_watermarks",
                "streambuild_deployments",
                "streambuild_object_state_snapshots",
                "streambuild_publish_history",
                "streambuild_state_schema_versions",
                "streambuild_target_ownership",
            ),
            expected_version_rows=((1,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_database_when_migrating_metadata_repeatedly_then_schema_is_idempotent(
    test_case: MetadataMigrationIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    connection: AdapterConnection = ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        connection.migrate_metadata_state(clickhouse_database)
        connection.migrate_metadata_state(clickhouse_database)
    finally:
        connection.close()

    table_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT name FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name LIKE 'streambuild_%' ORDER BY name"
    ).result_rows
    version_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT version FROM {clickhouse_database}.streambuild_state_schema_versions "
        "ORDER BY version"
    ).result_rows

    assert tuple(str(row[0]) for row in table_rows) == test_case.expected_table_names
    assert integer_rows(version_rows) == test_case.expected_version_rows


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        MetadataMigrationIntegrationTestCase(
            description="concurrent metadata migrations converge on one logical version",
            expected_table_names=(
                "streambuild_deployment_runtime_details",
                "streambuild_deployment_watermarks",
                "streambuild_deployments",
                "streambuild_object_state_snapshots",
                "streambuild_publish_history",
                "streambuild_state_schema_versions",
                "streambuild_target_ownership",
            ),
            expected_version_rows=((1,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_database_when_migrating_metadata_concurrently_then_attempts_are_safe(
    test_case: MetadataMigrationIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    start_barrier: Barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures: tuple[Future[None], ...] = (
            executor.submit(
                run_metadata_migration,
                connection_settings=clickhouse_connection_settings,
                database=clickhouse_database,
                start_barrier=start_barrier,
            ),
            executor.submit(
                run_metadata_migration,
                connection_settings=clickhouse_connection_settings,
                database=clickhouse_database,
                start_barrier=start_barrier,
            ),
        )
        _ = tuple(future.result() for future in futures)

    table_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT name FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name LIKE 'streambuild_%' ORDER BY name"
    ).result_rows
    version_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT DISTINCT version FROM "
        f"{clickhouse_database}.streambuild_state_schema_versions ORDER BY version"
    ).result_rows

    assert tuple(str(row[0]) for row in table_rows) == test_case.expected_table_names
    assert integer_rows(version_rows) == test_case.expected_version_rows


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        LegacyMetadataMigrationIntegrationTestCase(
            description="legacy five-table state gains additive schema without rewriting rows",
            runtime_details_setup_sql=(
                "CREATE TABLE {database}.streambuild_deployment_runtime_details ("
                "deployment_id String, root_database_name Nullable(String), "
                "root_object_type String, root_object_name String, state_kind String, "
                "replay_strategy String, active_deployment_id Nullable(String), "
                "anchor_database_name Nullable(String), anchor_object_type String, "
                "anchor_object_name String, anchor_physical_name Nullable(String), "
                "execution_mode Nullable(String), configured_backfill_mode Nullable(String), "
                "execution_lookback_seconds Nullable(Int64), live_target_names_json String) "
                "ENGINE = ReplacingMergeTree ORDER BY "
                "(deployment_id, root_object_type, root_object_name)"
            ),
            expected_deployment_row=(
                "legacy_deployment",
                "backfilling",
                "offsets",
                "[]",
            ),
            expected_object_state_count=1,
            expected_version_rows=((1,),),
            expected_legacy_deployment_count=1,
        ),
        LegacyMetadataMigrationIntegrationTestCase(
            description="legacy state missing optional runtime details recovers additively",
            runtime_details_setup_sql=(
                "DROP TABLE IF EXISTS {database}.streambuild_deployment_runtime_details"
            ),
            expected_deployment_row=(
                "legacy_deployment",
                "backfilling",
                "offsets",
                "[]",
            ),
            expected_object_state_count=1,
            expected_version_rows=((1,),),
            expected_legacy_deployment_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_legacy_metadata_when_migrating_then_rows_remain_readable_and_unmodified(
    test_case: LegacyMetadataMigrationIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.streambuild_object_state_snapshots ("
        "deployment_id String, database_name Nullable(String), object_type String, "
        "object_name String, normalized_fingerprint String, normalized_query Nullable(String), "
        "recorded_at DateTime64(3, 'UTC')) ENGINE = ReplacingMergeTree(recorded_at) "
        "ORDER BY (deployment_id, object_type, object_name)"
    )
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.streambuild_deployments ("
        "deployment_id String, created_at DateTime64(3, 'UTC'), status String, "
        "selected_root_keys_json String, warning_codes_json String, "
        "prepared_object_mappings_json String) ENGINE = ReplacingMergeTree(created_at) "
        "ORDER BY deployment_id"
    )
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.streambuild_deployment_watermarks ("
        "deployment_id String, root_database_name Nullable(String), root_object_type String, "
        "root_object_name String, anchor_database_name Nullable(String), "
        "anchor_object_type String, anchor_object_name String, boundary_key String, "
        "cutoff_value String) ENGINE = ReplacingMergeTree ORDER BY "
        "(deployment_id, root_object_type, root_object_name, boundary_key)"
    )
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.streambuild_publish_history ("
        "deployment_id String, published_at DateTime64(3, 'UTC'), "
        "logical_view_names_json String) ENGINE = ReplacingMergeTree(published_at) "
        "ORDER BY (deployment_id, published_at)"
    )
    clickhouse_client.command(
        test_case.runtime_details_setup_sql.format(database=clickhouse_database)
    )
    clickhouse_client.command(
        f"INSERT INTO {clickhouse_database}.streambuild_object_state_snapshots "
        "(deployment_id) VALUES "
        "('legacy_deployment')"
    )
    clickhouse_client.command(
        f"INSERT INTO {clickhouse_database}.streambuild_deployments "
        "(deployment_id, created_at, status, selected_root_keys_json, warning_codes_json, "
        "prepared_object_mappings_json) VALUES "
        "('legacy_deployment', '2026-01-01 00:00:00.000', 'backfilling', '[]', '[]', '[]')"
    )
    connection: AdapterConnection = ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        loaded_audit_deployment: LoadedAuditDeployment = load_audit_deployment(
            client=connection,
            metadata_database=clickhouse_database,
            deployment_id="legacy_deployment",
        )
        deployment_inventory: AdapterDeploymentInventory = connection.load_deployment_inventory(
            clickhouse_database
        )
        loaded_janitor_deployments: tuple[AdapterDeploymentRecord, ...] = (
            deployment_inventory.deployments
        )
        connection.migrate_metadata_state(clickhouse_database)
    finally:
        connection.close()

    deployment_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT deployment_id, status, replay_lineage_mode, selected_root_keys_json "
        f"FROM {clickhouse_database}.streambuild_deployments"
    ).result_rows
    object_state_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT count() FROM {clickhouse_database}.streambuild_object_state_snapshots"
    ).result_rows
    version_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT version FROM {clickhouse_database}.streambuild_state_schema_versions"
    ).result_rows

    assert tuple(str(value) for value in deployment_rows[0]) == test_case.expected_deployment_row
    assert str(loaded_audit_deployment.replay_lineage_mode) == test_case.expected_deployment_row[2]
    assert len(loaded_janitor_deployments) == test_case.expected_legacy_deployment_count
    assert (
        str(loaded_janitor_deployments[0].replay_lineage_mode)
        == (test_case.expected_deployment_row[2])
    )
    assert int(str(object_state_rows[0][0])) == test_case.expected_object_state_count
    assert integer_rows(version_rows) == test_case.expected_version_rows


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        TargetOwnershipIntegrationTestCase(
            description="durable ownership becomes readable only after rows are recorded",
            inserted_rows=(
                {
                    "database_name": "analytics",
                    "relation_name": "tbl__orders_enriched",
                    "resource_kind": "table",
                    "logical_model_database": "",
                    "logical_model_name": "orders_enriched",
                    "owning_mode": "standard",
                    "tool_version": "0.1.0",
                },
                {
                    "database_name": "analytics",
                    "relation_name": "mv__orders_enriched",
                    "resource_kind": "materialized_view",
                    "logical_model_database": "",
                    "logical_model_name": "orders_enriched",
                    "owning_mode": "virtual_environment",
                    "tool_version": "0.1.0",
                },
            ),
            expected_records_before_migration=(),
            expected_records_after_migration=(),
            expected_records_after_insert=(
                ("mv__orders_enriched", "orders_enriched", "virtual_environment"),
                ("tbl__orders_enriched", "orders_enriched", "standard"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_target_ownership_when_loading_then_durable_claims_are_returned(
    test_case: TargetOwnershipIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
) -> None:
    connection: AdapterConnection = connect_clickhouse(
        connection_settings=clickhouse_connection_settings,
        database=clickhouse_database,
    )

    try:
        connection.ensure_database(clickhouse_database)
        before_migration: tuple[AdapterOwnershipRecord, ...] = connection.load_target_ownership(
            clickhouse_database
        )
        connection.migrate_metadata_state(clickhouse_database)
        after_migration: tuple[AdapterOwnershipRecord, ...] = connection.load_target_ownership(
            clickhouse_database
        )
        connection.insert_rows(
            table=f"{clickhouse_database}.streambuild_target_ownership",
            rows=test_case.inserted_rows,
        )
        after_insert: tuple[AdapterOwnershipRecord, ...] = connection.load_target_ownership(
            clickhouse_database
        )
    finally:
        connection.close()

    assert ownership_summaries(before_migration) == test_case.expected_records_before_migration
    assert ownership_summaries(after_migration) == test_case.expected_records_after_migration
    assert ownership_summaries(after_insert) == test_case.expected_records_after_insert
