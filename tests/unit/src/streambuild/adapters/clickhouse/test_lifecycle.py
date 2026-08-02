import pytest

from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterIdentity,
    AdapterRelationCleanupRequest,
    CatalogIdentity,
    CatalogSnapshot,
    InspectedActiveTableBinding,
    InspectedManagedTableState,
)
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    ClickHouseCleanupProtectionTestCase,
)
from tests.unit.src.streambuild.adapters.clickhouse.helpers import (
    GuardedRenderingClickHouseConnection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseCleanupProtectionTestCase(
            description="refuses to drop a currently active ClickHouse target",
            active_relation_name="tbl__orders_enriched__20260727T110000Z_active1",
            expected_error_fragment="Refusing to clean active physical relation",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_relation_when_cleaning_clickhouse_then_it_fails_before_drop(
    test_case: ClickHouseCleanupProtectionTestCase,
) -> None:
    connection: GuardedRenderingClickHouseConnection = GuardedRenderingClickHouseConnection(
        catalog=CatalogSnapshot(
            identity=CatalogIdentity(
                adapter=AdapterIdentity(name="clickhouse"),
                database="analytics",
            ),
            warehouse_timezone="UTC",
            relations=(),
        ),
        managed_table_state=InspectedManagedTableState(
            active_bindings=(
                InspectedActiveTableBinding(
                    database="analytics",
                    logical_name="tbl__orders_enriched",
                    physical_name=test_case.active_relation_name,
                ),
            ),
            physical_candidates=(),
        ),
    )

    with pytest.raises(AdapterResultError, match=test_case.expected_error_fragment):
        connection.render_cleanup_relations(
            AdapterRelationCleanupRequest(
                database="analytics",
                relation_names=(test_case.active_relation_name,),
            )
        )

    assert connection.inspection_count == 1
