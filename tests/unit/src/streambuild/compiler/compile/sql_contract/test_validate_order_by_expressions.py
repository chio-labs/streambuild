import pytest

from streambuild.compiler.compile._helpers.sql_contract import (
    validate_order_by_expressions,
)
from streambuild.compiler.compile.exceptions import (
    TransformOrderByUnknownColumnError,
)
from tests.unit.src.streambuild.compiler.compile.sql_contract._test_types import (
    ValidateOrderByExpressionsTestCase,
)
from tests.unit.src.streambuild.compiler.compile.sql_contract.helpers import build_expected_columns

TEST_CASES: list[ValidateOrderByExpressionsTestCase] = [
    ValidateOrderByExpressionsTestCase(
        description="accepts simple and expression order by values that reference derived columns",
        order_by=("order_id", "toYYYYMM(created_at)"),
        available_columns=build_expected_columns(
            ("order_id", "UInt64"),
            ("created_at", "DateTime64(3)"),
        ),
        expected_error_type=None,
        expected_message_fragments=(),
        expected_error_attributes={},
    ),
    ValidateOrderByExpressionsTestCase(
        description="rejects order by expressions that reference unknown derived columns",
        order_by=("toYYYYMM(missing_created_at)",),
        available_columns=build_expected_columns(
            ("order_id", "UInt64"),
            ("created_at", "DateTime64(3)"),
        ),
        expected_error_type=TransformOrderByUnknownColumnError,
        expected_message_fragments=(
            "invalid ORDER BY expression",
            "missing_created_at",
            "Available columns: order_id, created_at",
        ),
        expected_error_attributes={
            "expression": "toYYYYMM(missing_created_at)",
            "unknown_column_names": ("missing_created_at",),
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_order_by_expressions_when_validating_then_it_returns_or_raises_as_expected(
    test_case: ValidateOrderByExpressionsTestCase,
) -> None:
    if test_case.expected_error_type is None:
        validate_order_by_expressions(
            "orders_enriched",
            test_case.order_by,
            test_case.available_columns,
        )
        assert test_case.expected_error_attributes == {}
        return

    with pytest.raises(test_case.expected_error_type) as error_info:
        validate_order_by_expressions(
            "orders_enriched",
            test_case.order_by,
            test_case.available_columns,
        )

    error: Exception = error_info.value
    for attribute_name, expected_value in test_case.expected_error_attributes.items():
        assert getattr(error, attribute_name) == expected_value

    error_message: str = str(error)
    for expected_fragment in test_case.expected_message_fragments:
        assert expected_fragment in error_message
