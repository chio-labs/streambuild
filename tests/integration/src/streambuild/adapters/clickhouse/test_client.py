import time
from concurrent.futures import Future, ThreadPoolExecutor

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterReplayOffsetFrontier,
    AdapterReplayOffsetProgressRequest,
    AdapterReplayOffsetRange,
    AdapterStatementProgress,
    AdapterWarehouseHealth,
    AdapterWarehouseTable,
    CatalogRelation,
    CatalogSnapshot,
)
from tests.integration.src.streambuild.adapters.clickhouse._test_types import (
    ClickHouseCatalogIntegrationTestCase,
    ClickHouseClientIntegrationTestCase,
    ClickHouseReplayProgressIntegrationTestCase,
    ClickHouseWarehouseHealthIntegrationTestCase,
    ClickHouseWarehouseTimestampIntegrationTestCase,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseClientIntegrationTestCase(
            description="creates a real client and executes command insert query and close",
            inserted_rows=(
                {"deployment_id": "dep_1", "status": "open"},
                {"deployment_id": "dep_2", "status": "failed"},
            ),
            expected_rows=(("dep_1", "open"), ("dep_2", "failed")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_clickhouse_when_using_client_then_it_executes_expected_operations(
    test_case: ClickHouseClientIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.deployments (deployment_id String, status String) "
        "ENGINE = MergeTree ORDER BY deployment_id"
    )

    clickhouse_client.insert(
        table=f"{clickhouse_database}.deployments",
        data=[list(row.values()) for row in test_case.inserted_rows],
        column_names=list(test_case.inserted_rows[0]),
    )

    result_rows: tuple[tuple[object, ...], ...] = managed_clickhouse_client.query(
        f"SELECT deployment_id, status FROM {clickhouse_database}.deployments "
        "ORDER BY deployment_id"
    ).rows

    assert result_rows == test_case.expected_rows


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseReplayProgressIntegrationTestCase(
            description="offset frontier remains logical while cascading views multiply query work",
            source_rows=20_000,
            expected_partition=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cascading_views_when_replaying_then_frontier_is_independent_of_read_rows(
    test_case: ClickHouseReplayProgressIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    root: str = f"{clickhouse_database}.replay_root"
    cascade_one: str = f"{clickhouse_database}.replay_cascade_one"
    cascade_two: str = f"{clickhouse_database}.replay_cascade_two"
    columns: str = "(_replay_partition Int64, _replay_offset Int64, value UInt64)"
    clickhouse_client.command(f"CREATE TABLE {root} {columns} ENGINE = MergeTree ORDER BY tuple()")
    clickhouse_client.command(
        f"CREATE TABLE {cascade_one} {columns} ENGINE = MergeTree ORDER BY tuple()"
    )
    clickhouse_client.command(
        f"CREATE TABLE {cascade_two} {columns} ENGINE = MergeTree ORDER BY tuple()"
    )
    clickhouse_client.command(
        f"CREATE MATERIALIZED VIEW {clickhouse_database}.replay_mv_one TO {cascade_one} "
        f"AS SELECT * FROM {root}"
    )
    clickhouse_client.command(
        f"CREATE MATERIALIZED VIEW {clickhouse_database}.replay_mv_two TO {cascade_two} "
        "AS SELECT _replay_partition, _replay_offset, "
        f"value + sleepEachRow(0.0001) AS value FROM {cascade_one}"
    )
    query_id: str = "replay-frontier-integration"
    replay_sql: str = (
        f"INSERT INTO {root} SELECT {test_case.expected_partition}, number, number "
        f"FROM numbers({test_case.source_rows}) SETTINGS max_threads = 1"
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future: Future[object] = executor.submit(
            clickhouse_client.command,
            replay_sql,
            settings={"query_id": query_id},
        )
        time.sleep(0.5)
        telemetry: AdapterStatementProgress | None = (
            managed_clickhouse_client.load_statement_progress(query_id=query_id)
        )
        frontiers: tuple[AdapterReplayOffsetFrontier, ...] | None = (
            managed_clickhouse_client.load_replay_offset_frontiers(
                query_id=query_id,
                request=AdapterReplayOffsetProgressRequest(
                    database=clickhouse_database,
                    relation="replay_root",
                    partition_column="_replay_partition",
                    offset_column="_replay_offset",
                    ranges=(
                        AdapterReplayOffsetRange(
                            partition=test_case.expected_partition,
                            lower_offset=0,
                            upper_offset=test_case.source_rows - 1,
                        ),
                    ),
                ),
            )
        )
        _ = future.result(timeout=10)

    assert telemetry is not None
    assert telemetry.read_rows > test_case.source_rows
    assert frontiers is not None
    assert frontiers == (
        AdapterReplayOffsetFrontier(
            partition=test_case.expected_partition,
            completed_offset=test_case.source_rows - 1,
        ),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseWarehouseTimestampIntegrationTestCase(
            description="captures the active ClickHouse server UTC DateTime64 millisecond clock",
            expected_fractional_digits=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_clickhouse_when_capturing_warehouse_time_then_returns_utc_milliseconds(
    test_case: ClickHouseWarehouseTimestampIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
) -> None:
    warehouse_timestamp: str = managed_clickhouse_client.capture_warehouse_timestamp()
    fractional_seconds: str = warehouse_timestamp.rsplit(".", 1)[1]

    assert len(fractional_seconds) == test_case.expected_fractional_digits


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseWarehouseHealthIntegrationTestCase(
            description="reads real capacity activity and project-scoped table footprint",
            table_name="warehouse_health_rows",
            expected_minimum_rows=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_clickhouse_project_when_reading_health_then_snapshot_is_bounded_and_usable(
    test_case: ClickHouseWarehouseHealthIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.{test_case.table_name} "
        "(id UInt64) ENGINE = MergeTree ORDER BY id"
    )
    clickhouse_client.command(
        f"INSERT INTO {clickhouse_database}.{test_case.table_name} VALUES (1), (2)"
    )

    health: AdapterWarehouseHealth = managed_clickhouse_client.load_warehouse_health(
        database=clickhouse_database
    )

    assert health.tables is not None
    tables_by_name: dict[str, AdapterWarehouseTable] = {item.name: item for item in health.tables}
    table: AdapterWarehouseTable = tables_by_name[test_case.table_name]
    assert str(health.availability) in {"available", "partial"}
    assert str(health.status) in {"healthy", "warning", "critical"}
    assert health.version
    assert health.uptime_seconds is not None
    assert health.disks
    assert health.activity is not None
    assert table.rows is not None
    assert table.rows >= test_case.expected_minimum_rows
    assert table.active_parts is not None
    assert table.active_parts >= 1


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseCatalogIntegrationTestCase(
            description="loads real tables views materialized views and Kafka settings",
            expected_relation_names=frozenset(
                {
                    "kafka__orders",
                    "mv__orders",
                    "tbl__orders",
                    "tbl__orders__dep_a",
                }
            ),
            expected_stable_binding_name="tbl__orders__dep_a",
            expected_materialized_view_source="kafka__orders",
            expected_materialized_view_target="tbl__orders__dep_a",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_relations_when_loading_catalog_then_it_returns_complete_snapshot(
    test_case: ClickHouseCatalogIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.tbl__orders__dep_a "
        "(order_id String, updated_at DateTime64(3) DEFAULT now64(3)) "
        "ENGINE = ReplacingMergeTree(updated_at) "
        "PARTITION BY toYYYYMM(updated_at) ORDER BY (order_id, updated_at) "
        "TTL toDateTime(updated_at) + INTERVAL 30 DAY SETTINGS index_granularity = 8192"
    )
    clickhouse_client.command(
        f"CREATE VIEW {clickhouse_database}.tbl__orders AS "
        f"SELECT * FROM {clickhouse_database}.tbl__orders__dep_a"
    )
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.kafka__orders (payload String) "
        "ENGINE = Kafka SETTINGS kafka_broker_list = 'redpanda:9092', "
        "kafka_topic_list = 'orders', kafka_group_name = 'streambuild', "
        "kafka_format = 'JSONEachRow'"
    )
    clickhouse_client.command(
        f"CREATE MATERIALIZED VIEW {clickhouse_database}.mv__orders "
        f"TO {clickhouse_database}.tbl__orders__dep_a AS "
        f"SELECT payload AS order_id, now64(3) AS updated_at "
        f"FROM {clickhouse_database}.kafka__orders"
    )

    catalog: CatalogSnapshot = managed_clickhouse_client.load_catalog(clickhouse_database)
    stable_view: CatalogRelation | None = catalog.relation("tbl__orders")
    physical_table: CatalogRelation | None = catalog.relation("tbl__orders__dep_a")
    kafka_table: CatalogRelation | None = catalog.relation("kafka__orders")
    materialized_view: CatalogRelation | None = catalog.relation("mv__orders")

    assert catalog.identity.database == clickhouse_database
    assert catalog.relation_names() == test_case.expected_relation_names
    assert stable_view is not None
    assert physical_table is not None
    assert kafka_table is not None
    assert materialized_view is not None
    assert stable_view.stable_binding_name == test_case.expected_stable_binding_name
    assert physical_table.order_by == ("order_id", "updated_at")
    assert physical_table.partition_by == "toYYYYMM(updated_at)"
    assert physical_table.ttl is not None
    assert physical_table.columns[1].default_expression == "now64(3)"
    assert ("kafka_format", "'JSONEachRow'") in kafka_table.settings
    assert materialized_view.source_relation_name == test_case.expected_materialized_view_source
    assert materialized_view.target_relation_name == test_case.expected_materialized_view_target
    assert materialized_view.query_sql is not None
