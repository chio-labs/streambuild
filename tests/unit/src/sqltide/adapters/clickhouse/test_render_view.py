import pytest

from sqltide.adapter.models import AdapterView
from sqltide.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.unit.src.sqltide.adapters.clickhouse._test_types import RenderViewTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        RenderViewTestCase(
            description="renders one ordinary view with database-qualified resolved references",
            database="analytics",
            view_name="customer_orders",
            database_template=("SELECT order_id\nFROM __sqltide_target_database__.orders_rollup"),
            expected_ddl=(
                "CREATE VIEW analytics.customer_orders AS\n"
                "SELECT order_id\nFROM analytics.orders_rollup"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ordinary_view_when_rendering_then_returns_create_view_ddl(
    test_case: RenderViewTestCase,
) -> None:
    rendered_ddl: str = ClickHouseAdapter().render_resource(
        resource=AdapterView(
            name=test_case.view_name,
            query="SELECT order_id FROM orders_rollup",
            database_template=test_case.database_template,
        ),
        database=test_case.database,
    )

    assert rendered_ddl == test_case.expected_ddl
