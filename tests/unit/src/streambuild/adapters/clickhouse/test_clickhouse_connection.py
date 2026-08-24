from typing import cast
from unittest.mock import MagicMock

import pytest
from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import (
    AdapterAuthenticationError,
    AdapterRelationNotFoundError,
    AdapterWarehouseError,
)
from streambuild.adapter.models import (
    AdapterQueryResult,
    AdapterStatementProgress,
    AdapterWarehouseDisk,
    AdapterWarehouseHealth,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.adapters.clickhouse.classes.clickhouse_connection import ClickHouseConnection
from streambuild.adapters.clickhouse.classes.warehouse_health_reader import (
    ClickHouseWarehouseHealthReader,
)
from streambuild.adapters.clickhouse.constants import CLICKHOUSE_UNKNOWN_CAPACITY_BYTES
from streambuild.adapters.clickhouse.types import RawClickHouseClient
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    CatalogInspectionTestCase,
    ClickHouseOptionalHealthFailureTestCase,
    ClickHousePublishCapabilitiesTestCase,
    ClickHouseStatementProgressTestCase,
    ClickHouseWarehouseHealthTestCase,
    ClickHouseWorkflowCorrelationTestCase,
    ConnectionQueryNormalizationTestCase,
    ConnectionTranslationTestCase,
)
from tests.unit.src.streambuild.adapters.clickhouse.helpers import (
    FailingRawClickHouseClient,
    FakeRawClickHouseQueryResult,
    SequencedRawClickHouseClient,
    StubRawClickHouseClient,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionTranslationTestCase(
            description="translates a workflow mutation relation failure",
            driver_error=DatabaseError(
                "Code: 60. DB::Exception: Table analytics.tbl__orders does not exist. "
                "(UNKNOWN_TABLE)"
            ),
            expected_error_type=AdapterRelationNotFoundError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_driver_when_executing_workflow_sql_then_it_raises_neutral_equivalent(
    test_case: ConnectionTranslationTestCase,
) -> None:
    connection: ClickHouseConnection = ClickHouseConnection(
        cast(RawClickHouseClient, FailingRawClickHouseClient(test_case.driver_error))
    )

    with pytest.raises(AdapterWarehouseError) as error_info:
        connection.execute_workflow_sql("DROP TABLE analytics.tbl__orders")

    assert type(error_info.value) is test_case.expected_error_type


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHousePublishCapabilitiesTestCase(
            description="reports per-relation but not graph-atomic ClickHouse publish",
            expected_stable_logical_bindings=True,
            expected_per_relation_atomic_replace=True,
            expected_graph_atomic_publish=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_connection_when_reading_publish_capabilities_then_guarantees_are_exact(
    test_case: ClickHousePublishCapabilitiesTestCase,
) -> None:
    raw_client: StubRawClickHouseClient = StubRawClickHouseClient(
        FakeRawClickHouseQueryResult(column_names=[], result_rows=[])
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))

    assert (
        connection.capabilities.stable_logical_bindings
        is test_case.expected_stable_logical_bindings
    )
    assert (
        connection.capabilities.per_relation_atomic_replace
        is test_case.expected_per_relation_atomic_replace
    )
    assert connection.capabilities.graph_atomic_publish is test_case.expected_graph_atomic_publish


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseWarehouseHealthTestCase(
            description="decodes bounded health and inclusive capacity thresholds",
            disk_rows=(
                ("critical", "/critical/", "Local", 0, 100, 6, 5, 0),
                ("warning", "/warning/", "Local", 0, 100, 16, 15, 0),
                ("healthy", "/healthy/", "Local", 0, 100, 20, 16, 0),
            ),
            metric_rows=(
                ("FilesystemMainPathTotalINodes", 1000),
                ("FilesystemMainPathAvailableINodes", 400),
                ("MemoryResident", 300),
                ("OSMemoryTotal", 2000),
                ("CGroupMemoryUsed", 500),
                ("CGroupMemoryTotal", 1000),
            ),
            expected_disk_statuses=("critical", "warning", "healthy"),
            expected_total_bytes=(100, 100, 100),
            expected_availability="available",
            expected_status="critical",
            expected_memory_basis="cgroup",
            expected_table_name="tbl__orders",
            expected_query_count=5,
        ),
        ClickHouseWarehouseHealthTestCase(
            description="does not infer overall health from inodes when disk capacity is unknown",
            disk_rows=(
                (
                    "remote",
                    "s3://warehouse/",
                    "ObjectStorage",
                    0,
                    CLICKHOUSE_UNKNOWN_CAPACITY_BYTES,
                    CLICKHOUSE_UNKNOWN_CAPACITY_BYTES,
                    CLICKHOUSE_UNKNOWN_CAPACITY_BYTES,
                    0,
                ),
            ),
            metric_rows=(
                ("FilesystemMainPathTotalINodes", 1000),
                ("FilesystemMainPathAvailableINodes", 50),
                ("MemoryResident", 300),
                ("OSMemoryTotal", 2000),
                ("CGroupMemoryUsed", 500),
                ("CGroupMemoryTotal", 1000),
            ),
            expected_disk_statuses=("unknown",),
            expected_total_bytes=(None,),
            expected_availability="partial",
            expected_status="unknown",
            expected_memory_basis="cgroup",
            expected_table_name="tbl__orders",
            expected_query_count=5,
        ),
        ClickHouseWarehouseHealthTestCase(
            description="broken disk dominates a healthy configured disk",
            disk_rows=(
                ("broken", "/broken/", "Local", 1, 0, 0, 0, 0),
                ("healthy", "/healthy/", "Local", 0, 100, 50, 50, 0),
            ),
            metric_rows=(
                ("FilesystemMainPathTotalINodes", 1000),
                ("FilesystemMainPathAvailableINodes", 900),
                ("MemoryResident", 300),
                ("OSMemoryTotal", 2000),
                ("CGroupMemoryUsed", 500),
                ("CGroupMemoryTotal", 1000),
            ),
            expected_disk_statuses=("critical", "healthy"),
            expected_total_bytes=(0, 100),
            expected_availability="available",
            expected_status="critical",
            expected_memory_basis="cgroup",
            expected_table_name="tbl__orders",
            expected_query_count=5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_system_metrics_when_reading_health_then_snapshot_is_truthful_and_bounded(
    test_case: ClickHouseWarehouseHealthTestCase,
) -> None:
    raw_client: SequencedRawClickHouseClient = SequencedRawClickHouseClient(
        (
            FakeRawClickHouseQueryResult(
                column_names=[
                    "name",
                    "path",
                    "type",
                    "is_broken",
                    "total_space",
                    "free_space",
                    "unreserved_space",
                    "keep_free_space",
                ],
                result_rows=[list(row) for row in test_case.disk_rows],
            ),
            FakeRawClickHouseQueryResult(
                column_names=["version", "uptime_seconds"],
                result_rows=[["25.8.1.1", 86400]],
            ),
            FakeRawClickHouseQueryResult(
                column_names=["metric", "value"],
                result_rows=[list(row) for row in test_case.metric_rows],
            ),
            FakeRawClickHouseQueryResult(
                column_names=["active_queries", "active_merges", "incomplete_mutations"],
                result_rows=[[2, 1, 3]],
            ),
            FakeRawClickHouseQueryResult(
                column_names=["table", "rows", "bytes_on_disk", "active_parts"],
                result_rows=[["tbl__orders", 500000, 64000000, 12]],
            ),
        )
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))

    health: AdapterWarehouseHealth = connection.load_warehouse_health("analytics\\o'")

    assert tuple(str(disk.status) for disk in health.disks) == test_case.expected_disk_statuses
    assert tuple(disk.total_bytes for disk in health.disks) == test_case.expected_total_bytes
    assert str(health.availability) == test_case.expected_availability
    assert str(health.status) == test_case.expected_status
    assert health.memory is not None
    assert health.memory.basis == test_case.expected_memory_basis
    assert health.memory.pressure_fraction == 0.5
    assert health.activity is not None
    assert health.activity.active_queries == 2
    assert health.tables is not None
    assert health.tables[0].name == test_case.expected_table_name
    assert len(raw_client.statements) == test_case.expected_query_count
    assert "query_id != currentQueryID()" in raw_client.statements[3]
    assert "database =" not in raw_client.statements[3]
    assert "database = 'analytics\\\\o'''" in raw_client.statements[4]
    assert "LIMIT 10" in raw_client.statements[4]


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseOptionalHealthFailureTestCase(
            description="failed project footprint remains unavailable rather than empty",
            expected_warning="Project table footprint is unavailable.",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_footprint_failure_when_reading_health_then_table_evidence_is_unavailable(
    test_case: ClickHouseOptionalHealthFailureTestCase,
) -> None:
    connection: MagicMock = MagicMock(spec=AdapterConnection)
    connection.query_many.side_effect = [
        (
            AdapterWarehouseDisk(
                name="default",
                path="/data/",
                disk_type="Local",
                total_bytes=100,
                free_bytes=50,
                unreserved_bytes=50,
                keep_free_bytes=0,
                status="healthy",
            ),
        ),
        (
            {"metric": "FilesystemMainPathTotalINodes", "value": 100},
            {"metric": "FilesystemMainPathAvailableINodes", "value": 50},
        ),
        AdapterWarehouseError("table probe failed"),
    ]
    connection.query_one.side_effect = [
        {"version": "25.8.1.1", "uptime_seconds": 100},
        {"active_queries": 0, "active_merges": 0, "incomplete_mutations": 0},
    ]

    health: AdapterWarehouseHealth = ClickHouseWarehouseHealthReader(
        connection=cast(AdapterConnection, connection)
    ).read(database="analytics")

    assert str(health.availability) == "partial"
    assert health.tables is None
    assert test_case.expected_warning in health.warnings


@pytest.mark.parametrize(
    "test_case",
    [
        CatalogInspectionTestCase(
            description="decodes a complete immutable catalog with three fixed queries",
            expected_timezone="America/New_York",
            expected_relation_names=frozenset({"tbl__orders", "tbl__orders__dep_a"}),
            expected_query_count=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_system_rows_when_loading_catalog_then_snapshot_is_complete(
    test_case: CatalogInspectionTestCase,
) -> None:
    raw_client: SequencedRawClickHouseClient = SequencedRawClickHouseClient(
        (
            FakeRawClickHouseQueryResult(
                column_names=["timezone()"],
                result_rows=[["America/New_York"]],
            ),
            FakeRawClickHouseQueryResult(
                column_names=[
                    "name",
                    "engine",
                    "sorting_key",
                    "partition_key",
                    "create_table_query",
                    "as_select",
                    "uuid",
                ],
                result_rows=[
                    [
                        "tbl__orders",
                        "View",
                        "",
                        "",
                        "CREATE VIEW analytics.tbl__orders AS "
                        "SELECT * FROM analytics.tbl__orders__dep_a",
                        "SELECT * FROM analytics.tbl__orders__dep_a",
                        "00000000-0000-0000-0000-000000000001",
                    ],
                    [
                        "tbl__orders__dep_a",
                        "ReplacingMergeTree",
                        "order_id, updated_at",
                        "toYYYYMM(updated_at)",
                        "CREATE TABLE analytics.tbl__orders__dep_a "
                        "(order_id String, updated_at DateTime64(3)) "
                        "ENGINE = ReplacingMergeTree(updated_at) "
                        "PARTITION BY toYYYYMM(updated_at) "
                        "ORDER BY (order_id, updated_at) "
                        "TTL updated_at + INTERVAL 30 DAY "
                        "SETTINGS index_granularity = 8192",
                        "",
                        "00000000-0000-0000-0000-000000000002",
                    ],
                ],
            ),
            FakeRawClickHouseQueryResult(
                column_names=["table", "name", "type", "default_expression"],
                result_rows=[
                    ["tbl__orders__dep_a", "order_id", "String", ""],
                    ["tbl__orders__dep_a", "updated_at", "DateTime64(3)", "now64(3)"],
                ],
            ),
        )
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))

    catalog: CatalogSnapshot = connection.load_catalog("analytics")
    relation: CatalogRelation | None = catalog.relation("tbl__orders__dep_a")
    binding: CatalogRelation | None = catalog.relation("tbl__orders")

    assert catalog.identity.adapter.name == "clickhouse"
    assert catalog.identity.database == "analytics"
    assert catalog.warehouse_timezone == test_case.expected_timezone
    assert catalog.relation_names() == test_case.expected_relation_names
    assert relation is not None
    assert binding is not None
    assert relation.engine == "ReplacingMergeTree"
    assert relation.order_by == ("order_id", "updated_at")
    assert relation.partition_by == "toYYYYMM(updated_at)"
    assert relation.ttl == "updated_at + INTERVAL '30' DAY"
    assert relation.settings == (("index_granularity", "8192"),)
    assert relation.columns[1].default_expression == "now64(3)"
    assert binding.stable_binding_name == "tbl__orders__dep_a"
    assert binding.source_relation_names == ("tbl__orders__dep_a",)
    assert binding.source_relation_name == "tbl__orders__dep_a"
    assert binding.query_sql == "SELECT * FROM analytics.tbl__orders__dep_a"
    assert len(raw_client.statements) == test_case.expected_query_count


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionQueryNormalizationTestCase(
            description="normalizes driver sequences into immutable neutral results",
            raw_column_names=["deployment_id", "status"],
            raw_result_rows=[["dep_1", "open"], ["dep_2", "failed"]],
            expected_column_names=("deployment_id", "status"),
            expected_rows=(("dep_1", "open"), ("dep_2", "failed")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_driver_rows_when_querying_through_the_adapter_then_it_returns_neutral_tuples(
    test_case: ConnectionQueryNormalizationTestCase,
) -> None:
    raw_client: StubRawClickHouseClient = StubRawClickHouseClient(
        FakeRawClickHouseQueryResult(
            column_names=test_case.raw_column_names,
            result_rows=test_case.raw_result_rows,
        )
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))

    result: AdapterQueryResult = connection.query("SELECT deployment_id, status FROM deployments")

    assert result.column_names == test_case.expected_column_names
    assert result.rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseWorkflowCorrelationTestCase(
            description="correlates workflow queries and mutations with ClickHouse query IDs",
            expected_query_ids=("query-123", "query-456"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_workflow_query_id_when_executing_then_clickhouse_parameter_correlates_request(
    test_case: ClickHouseWorkflowCorrelationTestCase,
) -> None:
    raw_client: StubRawClickHouseClient = StubRawClickHouseClient(
        FakeRawClickHouseQueryResult(column_names=[], result_rows=[])
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))

    connection.execute_workflow_query(statement="SELECT 1", query_id="query-123")
    connection.execute_workflow_mutation(statement="DROP TABLE test", query_id="query-456")

    assert raw_client.query_settings == [
        {"query_id": test_case.expected_query_ids[0]},
        {"query_id": test_case.expected_query_ids[1]},
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseStatementProgressTestCase(
            description="normalizes active ClickHouse process telemetry",
            expected_progress=AdapterStatementProgress(
                elapsed_seconds=12.5,
                read_rows=1000,
                read_bytes=2048,
                total_rows_approx=5000,
                memory_usage_bytes=4096,
                settings=(("max_threads", "1"),),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_clickhouse_process_when_loading_progress_then_telemetry_is_normalized(
    test_case: ClickHouseStatementProgressTestCase,
) -> None:
    raw_client: StubRawClickHouseClient = StubRawClickHouseClient(
        FakeRawClickHouseQueryResult(
            column_names=[
                "elapsed",
                "read_rows",
                "read_bytes",
                "total_rows_approx",
                "memory_usage",
                "settings",
            ],
            result_rows=[[12.5, 1000, 2048, 5000, 4096, {"max_threads": "1"}]],
        )
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))

    progress: AdapterStatementProgress | None = connection.load_statement_progress(
        query_id="query-123"
    )

    assert progress == test_case.expected_progress


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionTranslationTestCase(
            description="translates a query relation failure",
            driver_error=DatabaseError(
                "Code: 60. DB::Exception: Table analytics.tbl__orders does not exist. "
                "(UNKNOWN_TABLE)"
            ),
            expected_error_type=AdapterRelationNotFoundError,
        ),
        ConnectionTranslationTestCase(
            description="translates a query authentication failure",
            driver_error=OperationalError(
                "Code: 516. DB::Exception: Authentication failed. (AUTHENTICATION_FAILED)"
            ),
            expected_error_type=AdapterAuthenticationError,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_driver_when_querying_then_no_driver_exception_escapes(
    test_case: ConnectionTranslationTestCase,
) -> None:
    connection: ClickHouseConnection = ClickHouseConnection(
        cast(RawClickHouseClient, FailingRawClickHouseClient(test_case.driver_error))
    )

    with pytest.raises(AdapterWarehouseError) as error_info:
        connection.query("SELECT 1")

    assert type(error_info.value) is test_case.expected_error_type
    assert not isinstance(error_info.value, DatabaseError | OperationalError)


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionTranslationTestCase(
            description="translates a close failure",
            driver_error=DatabaseError(
                "Code: 60. DB::Exception: Connection target disappeared. (UNKNOWN_TABLE)"
            ),
            expected_error_type=AdapterRelationNotFoundError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_driver_when_closing_then_it_raises_the_neutral_equivalent(
    test_case: ConnectionTranslationTestCase,
) -> None:
    connection: ClickHouseConnection = ClickHouseConnection(
        cast(RawClickHouseClient, FailingRawClickHouseClient(test_case.driver_error))
    )

    with pytest.raises(AdapterWarehouseError) as error_info:
        connection.close()

    assert type(error_info.value) is test_case.expected_error_type
