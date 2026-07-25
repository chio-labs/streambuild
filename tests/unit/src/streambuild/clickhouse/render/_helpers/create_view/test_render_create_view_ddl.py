import pytest

from streambuild.clickhouse.render._helpers.create_view.main import render_create_view_ddl
from tests.unit.src.streambuild.clickhouse.render._helpers.create_view._test_types import (
    RenderCreateViewDdlTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderCreateViewDdlTestCase(
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
    ids=["renders stable logical view over deployment table"],
)
def test_given_view_target_when_rendering_then_it_returns_expected_create_view_ddl(
    test_case: RenderCreateViewDdlTestCase,
) -> None:
    rendered_ddl: str = render_create_view_ddl(
        database=test_case.database,
        view_name=test_case.view_name,
        target_table_name=test_case.target_table_name,
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered_ddl
