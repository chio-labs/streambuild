import pytest

from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import (
    AdapterOwnershipRecord,
    AdapterQueryResult,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.planner.main.load_planning_warehouse_snapshot import (
    load_planning_warehouse_snapshot,
)
from streambuild.compiler.planner.main.load_standard_warehouse_snapshot import (
    load_standard_warehouse_snapshot,
)
from streambuild.compiler.planner.models import (
    PlanningWarehouseSnapshot,
    StandardWarehouseSnapshot,
)
from tests.unit.src.streambuild.compiler.planner._test_types import (
    PlanningSnapshotAssemblyTestCase,
    PlanningSnapshotCapabilityTestCase,
)
from tests.unit.src.streambuild.compiler.planner.helpers import (
    SnapshotRecordingConnection,
    build_snapshot_catalog,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanningSnapshotAssemblyTestCase(
            description="captures the catalog and metadata exactly once",
            expected_catalog_load_count=1,
            expected_query_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_warehouse_state_when_loading_snapshot_then_it_reads_each_source_once(
    test_case: PlanningSnapshotAssemblyTestCase,
) -> None:
    catalog: CatalogSnapshot = build_snapshot_catalog()
    connection: SnapshotRecordingConnection = SnapshotRecordingConnection(
        catalog=catalog,
        metadata_result=AdapterQueryResult(
            column_names=(
                "deployment_id",
                "database_name",
                "object_type",
                "object_name",
                "normalized_fingerprint",
                "normalized_query",
                "recorded_at",
            ),
            rows=(("dep_a", None, "table", "tbl__orders", "fingerprint", None, "2026-07-26"),),
        ),
        virtual_environments=True,
    )

    snapshot: PlanningWarehouseSnapshot = load_planning_warehouse_snapshot(
        client=connection,
        database="analytics",
    )
    relation: CatalogRelation | None = snapshot.catalog.relation("tbl__orders")

    assert snapshot.catalog is catalog
    assert relation is not None
    assert relation.columns[0].name == "order_id"
    assert snapshot.object_state_records[0].deployment_id == "dep_a"
    assert snapshot.object_state_records[0].key.name == "tbl__orders"
    assert connection.catalog_load_count == test_case.expected_catalog_load_count
    assert connection.query_count == test_case.expected_query_count


@pytest.mark.parametrize(
    "test_case",
    [
        PlanningSnapshotCapabilityTestCase(
            description="rejects unsupported virtual environments before warehouse reads",
            expected_error_message=("Adapter 'clickhouse' does not support virtual environments"),
            expected_catalog_load_count=0,
            expected_query_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_capability_when_loading_snapshot_then_it_rejects_before_reads(
    test_case: PlanningSnapshotCapabilityTestCase,
) -> None:
    connection: SnapshotRecordingConnection = SnapshotRecordingConnection(
        catalog=build_snapshot_catalog(),
        metadata_result=AdapterQueryResult(rows=()),
        virtual_environments=False,
    )

    with pytest.raises(
        AdapterCapabilityError,
        match=test_case.expected_error_message,
    ):
        load_planning_warehouse_snapshot(client=connection, database="analytics")

    assert connection.catalog_load_count == test_case.expected_catalog_load_count
    assert connection.query_count == test_case.expected_query_count


@pytest.mark.parametrize(
    "test_case",
    [
        PlanningSnapshotAssemblyTestCase(
            description="reads the catalog and durable ownership exactly once each",
            expected_catalog_load_count=1,
            expected_query_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_capable_adapter_when_loading_standard_snapshot_then_it_reads_each_source_once(
    test_case: PlanningSnapshotAssemblyTestCase,
) -> None:
    catalog: CatalogSnapshot = build_snapshot_catalog()
    connection: SnapshotRecordingConnection = SnapshotRecordingConnection(
        catalog=catalog,
        metadata_result=AdapterQueryResult(rows=()),
        virtual_environments=False,
        ownership_records=(
            AdapterOwnershipRecord(
                database_name="analytics",
                relation_name="tbl__orders",
                resource_kind="table",
                logical_model_name="orders",
                owning_mode=AdapterOwningMode.STANDARD,
                tool_version="test",
            ),
        ),
    )

    snapshot: StandardWarehouseSnapshot = load_standard_warehouse_snapshot(
        client=connection,
        database="analytics",
    )

    assert snapshot.catalog is catalog
    assert snapshot.ownership_records[0].relation_name == "tbl__orders"
    assert connection.catalog_load_count == test_case.expected_catalog_load_count
    assert connection.query_count == test_case.expected_query_count


@pytest.mark.parametrize(
    "test_case",
    [
        PlanningSnapshotCapabilityTestCase(
            description="rejects adapters without standard rebuild support before warehouse reads",
            expected_error_message="Adapter 'clickhouse' does not support standard rebuilds",
            expected_catalog_load_count=0,
            expected_query_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_incapable_adapter_when_loading_standard_snapshot_then_it_rejects_before_reads(
    test_case: PlanningSnapshotCapabilityTestCase,
) -> None:
    connection: SnapshotRecordingConnection = SnapshotRecordingConnection(
        catalog=build_snapshot_catalog(),
        metadata_result=AdapterQueryResult(rows=()),
        virtual_environments=False,
        standard_rebuild=False,
    )

    with pytest.raises(AdapterCapabilityError, match=test_case.expected_error_message):
        load_standard_warehouse_snapshot(client=connection, database="analytics")

    assert connection.catalog_load_count == test_case.expected_catalog_load_count
    assert connection.query_count == test_case.expected_query_count
