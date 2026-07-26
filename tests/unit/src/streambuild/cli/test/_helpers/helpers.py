from pathlib import Path

from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery._helpers.testing.main import discover_sql_tests
from streambuild.compiler.shared.models import LoadedSqlTest
from tests.unit.src.streambuild.cli.shared.helpers import (
    compile_selector_project_pipelines,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.testing.helpers import (
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
