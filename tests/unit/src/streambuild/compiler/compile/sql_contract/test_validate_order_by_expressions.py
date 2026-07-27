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
from tests.unit.src.streambuild.compiler.compile.sql_contract.helpers import (
    build_expected_columns,
    build_sql_analyzer,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ValidateOrderByExpressionsTestCase(
            description=(
                "accepts simple and expression order by values that reference derived columns"
            ),
            order_by=("order_id", "toYYYYMM(created_at)"),
            available_columns=build_expected_columns(
                ("order_id", "UInt64"),
                ("created_at", "DateTime64(3)"),
            ),
            expected_error_type=None,
            expected_message_fragments=(),
            expected_error_attributes={},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_valid_order_by_expressions_when_validating_then_it_returns_normally(
    test_case: ValidateOrderByExpressionsTestCase,
) -> None:
    validate_order_by_expressions(
        analyzer=build_sql_analyzer(),
        transform_name="orders_enriched",
        order_by=test_case.order_by,
        available_columns=test_case.available_columns,
    )

    assert test_case.expected_error_attributes == {}


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_order_by_columns_when_validating_then_it_raises_contextual_error(
    test_case: ValidateOrderByExpressionsTestCase,
) -> None:
    expected_error_type: type[Exception] | None = test_case.expected_error_type
    assert expected_error_type is not None

    with pytest.raises(expected_error_type) as error_info:
        validate_order_by_expressions(
            analyzer=build_sql_analyzer(),
            transform_name="orders_enriched",
            order_by=test_case.order_by,
            available_columns=test_case.available_columns,
        )

    error: Exception = error_info.value
    for attribute_name, expected_value in test_case.expected_error_attributes.items():
        assert getattr(error, attribute_name) == expected_value

    error_message: str = str(error)
    for expected_fragment in test_case.expected_message_fragments:
        assert expected_fragment in error_message
