from pathlib import Path

import pytest

from streambuild.cli.test._helpers.rendering import render_sql_test_results
from streambuild.executor.testing.models import SqlTestExecutionResult, SqlTestTargetExecutionResult
from tests.unit.src.streambuild.cli.test._helpers._test_types import (
    RenderSqlTestResultsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderSqlTestResultsTestCase(
            description="renders side by side diff for keyed row changes",
            verbose=False,
            expected_fragments=(
                (
                    "FAIL  order_items  tests/order_events/test_line_total.sql  "
                    "[line total computes correctly]"
                ),
                "diff (1 row differs):",
                "columns: order_id, line_total",
                "row  state     order_id  line_total",
                "1    expected  ord_001   25.0",
                "1    actual    ord_001   20.0",
                "Results: 0 passed, 1 failed",
                "stb test tests/order_events/test_line_total.sql",
            ),
        ),
        RenderSqlTestResultsTestCase(
            description=(
                "renders aligned missing and unexpected tables when rows do not share a key"
            ),
            verbose=False,
            expected_fragments=(
                "missing rows (1):",
                "columns: order_id, line_total, region",
                "order_id  line_total  region",
                "ord_001   25.0        us-east",
                "unexpected rows (1):",
                "ord_004   99.0        ap-south",
            ),
        ),
        RenderSqlTestResultsTestCase(
            description="truncates long sections when not verbose",
            verbose=False,
            expected_fragments=(
                "unexpected rows (12, showing first 10):",
                "(2 more rows not shown, run with --verbose to see all)",
            ),
        ),
        RenderSqlTestResultsTestCase(
            description="renders all rows when verbose",
            verbose=True,
            expected_fragments=(
                "unexpected rows (12):",
                "ord_011",
                "ord_012",
            ),
        ),
        RenderSqlTestResultsTestCase(
            description="renders blank lines between failed multi target sections",
            verbose=False,
            expected_fragments=(
                "target: order_items\n  diff (1 row differs):",
                "\n\n  target: daily_revenue\n  diff (1 row differs):",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_results_when_rendering_then_it_returns_expected_sections(
    test_case: RenderSqlTestResultsTestCase,
) -> None:
    results: tuple[SqlTestExecutionResult, ...]
    if test_case.description == "renders side by side diff for keyed row changes":
        results = (
            SqlTestExecutionResult(
                file_path=Path("/project/tests/order_events/test_line_total.sql"),
                passed=False,
                target_results=(
                    SqlTestTargetExecutionResult(
                        target_model_name="order_items",
                        passed=False,
                        column_names=("order_id", "line_total"),
                        missing_rows=(("ord_001", 25.0),),
                        unexpected_rows=(("ord_001", 20.0),),
                    ),
                ),
                name="line total computes correctly",
            ),
        )
    elif (
        test_case.description
        == "renders aligned missing and unexpected tables when rows do not share a key"
    ):
        results = (
            SqlTestExecutionResult(
                file_path=Path("/project/tests/order_events/test_regions.sql"),
                passed=False,
                target_results=(
                    SqlTestTargetExecutionResult(
                        target_model_name="order_items",
                        passed=False,
                        column_names=("order_id", "line_total", "region"),
                        missing_rows=(("ord_001", 25.0, "us-east"),),
                        unexpected_rows=(("ord_004", 99.0, "ap-south"),),
                    ),
                ),
            ),
        )
    elif test_case.description == "renders blank lines between failed multi target sections":
        results = (
            SqlTestExecutionResult(
                file_path=Path("/project/tests/order_events/test_multi.sql"),
                passed=False,
                target_results=(
                    SqlTestTargetExecutionResult(
                        target_model_name="order_items",
                        passed=False,
                        column_names=("order_id", "line_total"),
                        missing_rows=(("ord_001", 25.0),),
                        unexpected_rows=(("ord_001", 20.0),),
                    ),
                    SqlTestTargetExecutionResult(
                        target_model_name="daily_revenue",
                        passed=False,
                        column_names=("order_id", "line_total"),
                        missing_rows=(("ord_001", 30.0),),
                        unexpected_rows=(("ord_001", 20.0),),
                    ),
                ),
            ),
        )
    else:
        results = (
            SqlTestExecutionResult(
                file_path=Path("/project/tests/order_events/test_many_rows.sql"),
                passed=False,
                target_results=(
                    SqlTestTargetExecutionResult(
                        target_model_name="order_items",
                        passed=False,
                        column_names=("order_id", "line_total"),
                        missing_rows=(),
                        unexpected_rows=tuple(
                            (f"ord_{index:03d}", float(index)) for index in range(1, 13)
                        ),
                    ),
                ),
            ),
        )

    rendered: str = render_sql_test_results(
        results=results,
        project_dir=Path("/project"),
        verbose=test_case.verbose,
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered
