from pathlib import Path

import pytest

from streambuild.compiler.testing.models import SqlTestCase
from tests.unit.src.streambuild.compiler.testing._test_types import (
    BuildSqlTestCasesErrorTestCase,
    MacroSqlTestAssemblyTestCase,
    SqlTestAssertionAssemblyTestCase,
)
from tests.unit.src.streambuild.compiler.testing.helpers import (
    build_cyclic_sql_test_case,
    build_single_sql_test_case,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestAssertionAssemblyTestCase(
            description="resolves an assertion reference through the assembled real chain",
            test_file_contents="""
        TEST ();

        WITH
        __source__orders AS (
          SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
        ),
        __assert__line_totals_are_not_null AS (
          SELECT order_id FROM __ref("order_items") WHERE line_total IS NULL
        )
        SELECT 1
        """,
            expected_assertion_names=("line_totals_are_not_null",),
            expected_assertion_column_names=("order_id",),
            expected_query_fragments=(
                "__model__order_items",
                "FROM __model__order_items",
                "'unexpected' AS _diff_type",
            ),
        ),
        SqlTestAssertionAssemblyTestCase(
            description="assembles assertions after expected targets in one statement",
            test_file_contents="""
        TEST ();

        WITH
        __source__orders AS (
          SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
        ),
        __expected__order_items AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
        ),
        __assert__no_negative_totals AS (
          SELECT order_id FROM __ref("order_items") WHERE line_total < 0
        )
        SELECT 1
        """,
            expected_assertion_names=("no_negative_totals",),
            expected_assertion_column_names=("order_id",),
            expected_query_fragments=("0 AS _case_index", "1 AS _case_index"),
        ),
        SqlTestAssertionAssemblyTestCase(
            description="keeps helper ctes in scope for an assertion",
            test_file_contents="""
        TEST ();

        WITH
        helper_orders AS (
          SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
        ),
        __source__orders AS (
          SELECT * FROM helper_orders
        ),
        allowed_orders AS (
          SELECT 'ord_001' AS order_id
        ),
        __assert__only_allowed_orders AS (
          SELECT order_id FROM __ref("order_items")
          WHERE order_id NOT IN (SELECT order_id FROM allowed_orders)
        )
        SELECT 1
        """,
            expected_assertion_names=("only_allowed_orders",),
            expected_assertion_column_names=("order_id",),
            expected_query_fragments=("helper_orders AS", "allowed_orders AS"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_authored_assertions_when_assembling_then_it_builds_zero_row_targets(
    test_case: SqlTestAssertionAssemblyTestCase,
    tmp_path: Path,
) -> None:
    assembled: SqlTestCase = build_single_sql_test_case(
        tmp_path=tmp_path,
        test_file_contents=test_case.test_file_contents,
    )

    assert tuple(assertion.name for assertion in assembled.assertion_cases) == (
        test_case.expected_assertion_names
    )
    assert assembled.assertion_cases[0].column_names == test_case.expected_assertion_column_names
    expected_fragment: str
    for expected_fragment in test_case.expected_query_fragments:
        assert expected_fragment in assembled.query


@pytest.mark.parametrize(
    "test_case",
    [
        MacroSqlTestAssemblyTestCase(
            description="compares an expanded macro result against its authored expectation",
            test_file_contents="""
        TEST (mode macro, name "doubles the value");

        WITH
        input_values AS (
          SELECT 21 AS base_value
        ),
        __macro_actual__ AS (
          SELECT base_value * 2 AS doubled FROM input_values
        ),
        __macro_expected__ AS (
          SELECT 42 AS doubled
        )
        SELECT 1
        """,
            expected_target_model_name="macro doubles the value",
            expected_column_names=("doubled",),
            expected_query_fragments=(
                "input_values AS",
                "base_value * 2 AS doubled",
                "SELECT 42 AS doubled",
                "isNotDistinctFrom(expected_rows.doubled, actual_rows.doubled)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_macro_mode_test_when_assembling_then_it_builds_one_macro_comparison(
    test_case: MacroSqlTestAssemblyTestCase,
    tmp_path: Path,
) -> None:
    assembled: SqlTestCase = build_single_sql_test_case(
        tmp_path=tmp_path,
        test_file_contents=test_case.test_file_contents,
    )

    assert assembled.target_cases[0].target_model_name == test_case.expected_target_model_name
    assert assembled.target_cases[0].expected_column_names == test_case.expected_column_names
    assert assembled.assertion_cases == ()
    expected_fragment: str
    for expected_fragment in test_case.expected_query_fragments:
        assert expected_fragment in assembled.query


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSqlTestCasesErrorTestCase(
            description="rejects a macro test whose sides project different column names",
            test_file_contents="""
        TEST (mode macro, name "mismatched projections");

        WITH
        __macro_actual__ AS (
          SELECT 42 AS doubled
        ),
        __macro_expected__ AS (
          SELECT 42 AS expected_value
        )
        SELECT 1
        """,
            expected_error_fragment="must project the same column names",
        ),
        BuildSqlTestCasesErrorTestCase(
            description="rejects an assertion whose reference cannot be resolved",
            test_file_contents="""
        TEST ();

        WITH
        __ref__order_items AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
        ),
        __assert__unknown_relation AS (
          SELECT order_id FROM __ref("missing_model")
        )
        SELECT 1
        """,
            expected_error_fragment="dependency 'missing_model' cannot be resolved",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_assertion_or_macro_test_when_assembling_then_it_raises_clear_errors(
    test_case: BuildSqlTestCasesErrorTestCase,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_single_sql_test_case(
            tmp_path=tmp_path,
            test_file_contents=test_case.test_file_contents,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSqlTestCasesErrorTestCase(
            description="fails a cyclic model chain before any adapter execution",
            test_file_contents="""
        TEST ();

        WITH
        __source__orders AS (
          SELECT 'ord_001' AS order_id
        ),
        __expected__loop_a AS (
          SELECT 'ord_001' AS order_id
        )
        SELECT 1
        """,
            expected_error_fragment="has a driving-input cycle: loop_a, loop_b",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cyclic_model_chain_when_assembling_then_it_fails_before_execution(
    test_case: BuildSqlTestCasesErrorTestCase,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_cyclic_sql_test_case(
            tmp_path=tmp_path,
            test_file_contents=test_case.test_file_contents,
        )
