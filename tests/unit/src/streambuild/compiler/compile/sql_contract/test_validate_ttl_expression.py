import pytest

from streambuild.compiler.compile._helpers.sql_contract import (
    validate_ttl_expression,
)
from streambuild.compiler.compile.exceptions import (
    TransformTtlUnknownColumnError,
)
from tests.unit.src.streambuild.compiler.compile.sql_contract._test_types import (
    ValidateSingleStorageExpressionTestCase,
)
from tests.unit.src.streambuild.compiler.compile.sql_contract.helpers import build_expected_columns

TEST_CASES: list[ValidateSingleStorageExpressionTestCase] = [
    ValidateSingleStorageExpressionTestCase(
        description="accepts ttl expressions that reference derived columns",
        expression="toDateTime(created_at) + INTERVAL 30 DAY",
        available_columns=build_expected_columns(
            ("order_id", "UInt64"),
            ("created_at", "DateTime64(3)"),
        ),
        expected_error_type=None,
        expected_message_fragments=(),
        expected_error_attributes={},
    ),
    ValidateSingleStorageExpressionTestCase(
        description="rejects ttl expressions that reference unknown derived columns",
        expression="toDateTime(missing_created_at) + INTERVAL 30 DAY",
        available_columns=build_expected_columns(
            ("order_id", "UInt64"),
            ("created_at", "DateTime64(3)"),
        ),
        expected_error_type=TransformTtlUnknownColumnError,
        expected_message_fragments=(
            "invalid TTL expression",
            "missing_created_at",
            "Available columns: order_id, created_at",
        ),
        expected_error_attributes={
            "expression": "toDateTime(missing_created_at) + INTERVAL 30 DAY",
            "unknown_column_names": ("missing_created_at",),
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_ttl_expression_when_validating_then_it_returns_or_raises_as_expected(
    test_case: ValidateSingleStorageExpressionTestCase,
) -> None:
    if test_case.expected_error_type is None:
        validate_ttl_expression(
            transform_name="orders_enriched",
            ttl=test_case.expression,
            available_columns=test_case.available_columns,
        )
        assert test_case.expected_error_attributes == {}
        return

    with pytest.raises(test_case.expected_error_type) as error_info:
        validate_ttl_expression(
            transform_name="orders_enriched",
            ttl=test_case.expression,
            available_columns=test_case.available_columns,
        )

    error: Exception = error_info.value
    for attribute_name, expected_value in test_case.expected_error_attributes.items():
        assert getattr(error, attribute_name) == expected_value

    error_message: str = str(error)
    for expected_fragment in test_case.expected_message_fragments:
        assert expected_fragment in error_message
