from pathlib import Path

import pytest

from streambuild.compiler.testing.main import build_sql_test_cases
from streambuild.compiler.testing.models import SqlTestCase
from tests.unit.src.streambuild.compiler.testing._test_types import (
    BuildSqlTestCasesErrorTestCase,
    BuildSqlTestCasesTestCase,
)
from tests.unit.src.streambuild.compiler.testing.helpers import build_compiled_pipeline_with_tests

TEST_CASES: list[BuildSqlTestCasesTestCase] = [
    BuildSqlTestCasesTestCase(
        description="assembles the minimum chain from source mock through target model",
        test_file_contents="""
        TEST ();

        WITH
        __source__orders AS (
          SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
        ),
        __expected__daily_revenue AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
        )
        SELECT 1
        """,
        expected_query_fragments=(
            "__source__orders AS",
            "__model__order_items AS",
            "FROM __model__daily_revenue",
            "CAST(line_total AS Nullable(Float64)) AS line_total",
        ),
        expected_target_model_names=("daily_revenue",),
    ),
    BuildSqlTestCasesTestCase(
        description="stops at direct ref mocks instead of compiling upstream models",
        test_file_contents="""
        TEST ();

        WITH
        __ref__order_items AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
        ),
        __expected__daily_revenue AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
        )
        SELECT 1
        """,
        expected_query_fragments=(
            "__ref__order_items AS",
            "FROM __ref__order_items",
        ),
        expected_absent_fragments=("__model__order_items AS",),
        expected_target_model_names=("daily_revenue",),
    ),
    BuildSqlTestCasesTestCase(
        description="preserves helper ctes and infers expected columns through select star",
        test_file_contents="""
        TEST ();

        WITH
        mock_rows AS (
          SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
        ),
        __source__orders AS (
          SELECT * FROM mock_rows
        ),
        expected_rows AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
        ),
        __expected__order_items AS (
          SELECT * FROM expected_rows
        )
        SELECT 1
        """,
        expected_query_fragments=(
            "mock_rows AS",
            "__source__orders AS",
            "expected_rows AS",
            "CAST(order_id AS String) AS order_id",
            "CAST(line_total AS Nullable(Float64)) AS line_total",
        ),
        expected_target_model_names=("order_items",),
    ),
    BuildSqlTestCasesTestCase(
        description="supports expected unions directly",
        test_file_contents="""
        TEST ();

        WITH
        __ref__orders AS (
          SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
          UNION ALL
          SELECT 'ord_002' AS order_id, NULL AS quantity, 5.0 AS unit_price
        ),
        __expected__order_items AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
          UNION ALL
          SELECT 'ord_002' AS order_id, NULL AS line_total
        )
        SELECT 1
        """,
        expected_query_fragments=(
            "CAST(order_id AS String) AS order_id",
            "CAST(line_total AS Nullable(Float64)) AS line_total",
            "UNION ALL",
        ),
        expected_target_model_names=("order_items",),
    ),
    BuildSqlTestCasesTestCase(
        description="supports multi branch expected unions using first branch column names",
        test_file_contents="""
        TEST ();

        WITH
        __ref__orders AS (
          SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
          UNION ALL
          SELECT 'ord_002' AS order_id, NULL AS quantity, 5.0 AS unit_price
          UNION ALL
          SELECT 'ord_003' AS order_id, 1 AS quantity, 7.5 AS unit_price
        ),
        __expected__order_items AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
          UNION ALL
          SELECT 'ord_002', NULL
          UNION ALL
          SELECT 'ord_003', 7.5
        )
        SELECT 1
        """,
        expected_query_fragments=(
            "CAST(order_id AS String) AS order_id",
            "CAST(line_total AS Nullable(Float64)) AS line_total",
            "SELECT 'ord_003', 7.5",
        ),
        expected_target_model_names=("order_items",),
    ),
    BuildSqlTestCasesTestCase(
        description="supports multiple expected targets in one scenario",
        test_file_contents="""
        TEST ();

        WITH
        __source__orders AS (
          SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
        ),
        __expected__order_items AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
        ),
        __expected__daily_revenue AS (
          SELECT 'ord_001' AS order_id, 20.0 AS line_total
        )
        SELECT 1
        """,
        expected_query_fragments=(
            "FROM __model__order_items",
            "FROM __model__daily_revenue",
        ),
        expected_target_model_names=("order_items", "daily_revenue"),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_discovered_sql_tests_when_building_cases_then_it_assembles_expected_queries(
    test_case: BuildSqlTestCasesTestCase,
    tmp_path: Path,
) -> None:
    compiled_pipeline, loaded_test = build_compiled_pipeline_with_tests(
        tmp_path=tmp_path,
        test_file_contents=test_case.test_file_contents,
    )

    test_case_result: SqlTestCase = build_sql_test_cases(
        loaded_tests=(loaded_test,),
        compiled_pipelines=(compiled_pipeline,),
    )[0]

    assert tuple(
        target_case.target_model_name for target_case in test_case_result.target_cases
    ) == (test_case.expected_target_model_names)
    for expected_fragment in test_case.expected_query_fragments:
        assert any(
            expected_fragment in target_case.query for target_case in test_case_result.target_cases
        )
    for expected_absent_fragment in test_case.expected_absent_fragments:
        assert all(
            expected_absent_fragment not in target_case.query
            for target_case in test_case_result.target_cases
        )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSqlTestCasesErrorTestCase(
            description="raises a clear error for unresolved source dependencies",
            test_file_contents="""
            TEST ();

            WITH
            __ref__region_lookup AS (
              SELECT 'north' AS region, 'NORTH' AS region_display
            ),
            __expected__daily_revenue AS (
              SELECT 'ord_001' AS order_id, 20.0 AS line_total
            )
            SELECT 1
            """,
            expected_error_fragment="dependency 'orders' cannot be resolved",
        )
    ],
    ids=["raises a clear error for unresolved source dependencies"],
)
def test_given_invalid_sql_tests_when_building_cases_then_it_raises_clear_errors(
    test_case: BuildSqlTestCasesErrorTestCase,
    tmp_path: Path,
) -> None:
    compiled_pipeline, loaded_test = build_compiled_pipeline_with_tests(
        tmp_path=tmp_path,
        test_file_contents=test_case.test_file_contents,
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_sql_test_cases(
            loaded_tests=(loaded_test,),
            compiled_pipelines=(compiled_pipeline,),
        )
