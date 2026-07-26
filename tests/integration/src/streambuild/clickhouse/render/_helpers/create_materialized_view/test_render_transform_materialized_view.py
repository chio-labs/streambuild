from collections.abc import Sequence

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.clickhouse.render._helpers.create_materialized_view import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render._helpers.create_table import render_create_table_ddl
from streambuild.compiler.compile.models import CompiledPipeline
from tests.integration.src.streambuild.clickhouse.render._helpers.create_materialized_view._test_types import (  # noqa: E501
    RenderTransformMaterializedViewIntegrationTestCase,
)
from tests.integration.src.streambuild.clickhouse.render._helpers.create_materialized_view.helpers import (  # noqa: E501
    build_compiled_example_pipeline,
    build_raw_orders_row,
)
from tests.integration.src.streambuild.executor.backfill.helpers import require_managed_source


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        RenderTransformMaterializedViewIntegrationTestCase(
            description="applies compiled transform materialized view against real clickhouse",
            expected_order_id="order-1",
            expected_customer_id="customer-7",
            expected_order_total=42.5,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_transform_mv_when_applied_to_real_clickhouse_then_it_populates_target_table(
    test_case: RenderTransformMaterializedViewIntegrationTestCase,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_compiled_example_pipeline()

    clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table, database=clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=compiled_pipeline.transforms[0].target_table, database=clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=compiled_pipeline.transforms[0].materialized_view,
            database=clickhouse_database,
        )
    )

    clickhouse_client.insert(
        table=f"{clickhouse_database}.{require_managed_source(compiled_pipeline).raw_table.name}",
        data=[build_raw_orders_row()],
        column_names=[
            column.name for column in require_managed_source(compiled_pipeline).raw_table.columns
        ],
    )

    result_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id, customer_id, order_total FROM "
        f"{clickhouse_database}.{compiled_pipeline.transforms[0].target_table.name}"
    ).result_rows

    assert result_rows == [
        (
            test_case.expected_order_id,
            test_case.expected_customer_id,
            test_case.expected_order_total,
        )
    ]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
