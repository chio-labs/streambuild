import pytest

from streambuild.adapter.models import AdapterStableView
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    RenderStableViewTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderStableViewTestCase(
            description="renders stable logical view over deployment table",
            database="analytics",
            view_name="tbl__orders_enriched",
            target_table_name="tbl__orders_enriched__20260409T180000Z_ab12cd",
            expected_fragments=(
                "CREATE OR REPLACE VIEW analytics.tbl__orders_enriched AS",
                "SELECT * FROM analytics.tbl__orders_enriched__20260409T180000Z_ab12cd",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_view_target_when_rendering_then_it_returns_expected_create_view_ddl(
    test_case: RenderStableViewTestCase,
) -> None:
    rendered_ddl: str = ClickHouseAdapter().render_resource(
        resource=AdapterStableView(
            name=test_case.view_name,
            target_relation_name=test_case.target_table_name,
        ),
        database=test_case.database,
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered_ddl
