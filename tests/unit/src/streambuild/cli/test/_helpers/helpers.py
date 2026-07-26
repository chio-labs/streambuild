from pathlib import Path

from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.test_discovery.main.discover_sql_tests import discover_sql_tests
from streambuild.compiler.test_discovery.models import LoadedSqlTest
from streambuild.executor.testing.models import SqlTestExecutionResult, SqlTestTargetExecutionResult
from tests.unit.src.streambuild.cli.plan.main.helpers import (
    compile_selector_project_pipelines,
)
from tests.unit.src.streambuild.compiler.test_discovery.helpers import (
    write_sql_test_file,
)


def build_selector_project_loaded_tests(tmp_path: Path) -> tuple[LoadedSqlTest, ...]:
    tests_root: Path = tmp_path / "tests"
    write_sql_test_file(
        tests_root / "orders" / "test_orders_clean.sql",
        """
        TEST ();

        WITH
        __source__orders AS (
          SELECT '{"order_id":"ord_001"}' AS kafka_value,
                 now64(3) AS _replay_landed_at
        ),
        __expected__orders_clean AS (
          SELECT 'ord_001' AS order_id, now64(3) AS _replay_landed_at
        )
        SELECT 1
        """,
    )
    write_sql_test_file(
        tests_root / "orders" / "test_orders_enriched.sql",
        """
        TEST ();

        WITH
        __ref__orders_clean AS (
          SELECT 'ord_001' AS order_id, now64(3) AS _replay_landed_at
        ),
        __expected__orders_enriched AS (
          SELECT 'ord_001' AS order_id, now64(3) AS _replay_landed_at
        )
        SELECT 1
        """,
    )
    write_sql_test_file(
        tests_root / "payments" / "test_payments_enriched.sql",
        """
        TEST ();

        WITH
        __source__payments AS (
          SELECT '{"payment_id":"pay_001"}' AS kafka_value,
                 now64(3) AS _replay_landed_at
        ),
        __expected__payments_enriched AS (
          SELECT 'pay_001' AS payment_id, now64(3) AS _replay_landed_at
        )
        SELECT 1
        """,
    )
    return tuple(discover_sql_tests(tests_root))


def build_selector_project_compiled_pipelines() -> tuple[CompiledPipeline, ...]:
    return compile_selector_project_pipelines()


def build_render_sql_test_results(description: str) -> tuple[SqlTestExecutionResult, ...]:
    results_by_description: dict[str, tuple[SqlTestExecutionResult, ...]] = {
        "renders side by side diff for keyed row changes": (
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
        ),
        "renders aligned missing and unexpected tables when rows do not share a key": (
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
        ),
        "renders blank lines between failed multi target sections": (
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
        ),
        "truncates long sections when not verbose": (
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
        ),
        "renders all rows when verbose": (
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
        ),
    }
    return results_by_description[description]
