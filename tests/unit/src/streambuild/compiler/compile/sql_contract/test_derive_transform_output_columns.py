import pytest

from streambuild.compiler.compile._helpers.sql_contract import derive_transform_output_columns
from tests.unit.src.streambuild.compiler.compile.sql_contract._test_types import (
    DeriveTransformOutputColumnsSuccessTestCase,
)
from tests.unit.src.streambuild.compiler.compile.sql_contract.helpers import build_expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        DeriveTransformOutputColumnsSuccessTestCase(
            description="derives output columns from a single strict select",
            query="""
            SELECT
                CAST(order_id AS UInt64) AS order_id,
                CAST(created_at AS DateTime64(3)) AS created_at
            FROM staged
        """,
            expected_columns=build_expected_columns(
                ("order_id", "UInt64"),
                ("created_at", "DateTime64(3)"),
            ),
        ),
        DeriveTransformOutputColumnsSuccessTestCase(
            description="derives output columns from a cte-backed final select",
            query="""
            WITH staged AS (
                SELECT
                    raw_order_id,
                    raw_created_at
                FROM source_events
                UNION ALL
                SELECT
                    raw_order_id,
                    raw_created_at
                FROM source_replays
            )
            SELECT
                CAST(raw_order_id AS UInt64) AS order_id,
                CAST(parseDateTime64BestEffort(raw_created_at, 3) AS DateTime64(3)) AS created_at
            FROM staged
        """,
            expected_columns=build_expected_columns(
                ("order_id", "UInt64"),
                ("created_at", "DateTime64(3)"),
            ),
        ),
        DeriveTransformOutputColumnsSuccessTestCase(
            description="derives output columns from clickhouse double-colon casts",
            query="""
            SELECT
                order_id::UInt64 AS order_id,
                parseDateTime64BestEffort(created_at, 3)::DateTime64(3) AS created_at
            FROM staged
        """,
            expected_columns=build_expected_columns(
                ("order_id", "UInt64"),
                ("created_at", "DateTime64(3)"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_transform_sql_when_deriving_output_columns_then_it_returns_expected_columns(
    test_case: DeriveTransformOutputColumnsSuccessTestCase,
) -> None:
    derived_columns: tuple = derive_transform_output_columns(
        transform_name="orders_enriched", query=test_case.query
    )

    assert derived_columns == test_case.expected_columns
