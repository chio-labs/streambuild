from pathlib import Path

import pytest
from _pytest.capture import CaptureResult
from clickhouse_connect.driver.client import Client

from streambuild.cli.commands.main.test.main import run_test
from streambuild.integrations.clickhouse.client import ClickHouseClient
from tests.integration.src.streambuild.cli.commands._test_types import (
    CliTestCommandIntegrationTestCase,
)
from tests.integration.src.streambuild.cli.commands.helpers import build_managed_clickhouse_client
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import write_pipeline_file
from tests.unit.src.streambuild.compiler.discovery._helpers.testing.helpers import (
    write_sql_test_file,
)

TEST_CASES: list[CliTestCommandIntegrationTestCase] = [
    CliTestCommandIntegrationTestCase(
        description="reports a passing SQL-native test result",
        selectors=("order_items",),
        expected_exit_code=0,
        expected_output_fragments=(
            "PASS",
            "order_items",
            "tests/order_events/test_line_total.sql",
            "Results: 1 passed, 0 failed",
        ),
    ),
    CliTestCommandIntegrationTestCase(
        description="runs multiple sql tests from one file",
        selectors=(),
        expected_exit_code=0,
        expected_output_fragments=(
            "PASS",
            "tests/order_events/test_line_total.sql  [line total computes correctly]",
            "tests/order_events/test_line_total.sql  [line total remains stable on repeat]",
            "Results: 2 passed, 0 failed",
        ),
    ),
    CliTestCommandIntegrationTestCase(
        description="renders grouped missing and unexpected rows for failures",
        selectors=("order_items",),
        expected_exit_code=1,
        expected_output_fragments=(
            "FAIL",
            "order_items",
            "diff (1 row differs):",
            "columns: order_id, line_total",
            "row  state     order_id  line_total",
            "1    expected  ord_001   25.0",
            "1    actual    ord_001   20.0",
            "Failed:",
            "stb test tests/order_events/test_line_total.sql",
        ),
    ),
    CliTestCommandIntegrationTestCase(
        description="renders grouped failures for multiple expected targets in one test",
        selectors=("order_items",),
        expected_exit_code=1,
        expected_output_fragments=(
            "FAIL",
            "order_items, daily_revenue",
            "target: order_items",
            "target: daily_revenue",
            "stb test tests/order_events/test_line_total.sql",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
@pytest.mark.integration
def test_given_sql_native_test_project_when_running_test_command_then_it_reports_expected_results(
    test_case: CliTestCommandIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = tmp_path / "pipelines" / "order_events" / "pipeline.yml"
    transform_file_path: Path = tmp_path / "pipelines" / "order_events" / "order_items.sql"
    downstream_file_path: Path = tmp_path / "pipelines" / "order_events" / "daily_revenue.sql"
    test_file_path: Path = tmp_path / "tests" / "order_events" / "test_line_total.sql"
    downstream_test_file_path: Path = tmp_path / "tests" / "order_events" / "test_daily_revenue.sql"
    write_pipeline_file(
        pipeline_file_path,
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
    )
    write_pipeline_file(
        transform_file_path,
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    )
    write_pipeline_file(
        downstream_file_path,
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(line_total AS Nullable(Float64)) AS line_total
        FROM __ref("order_items")
        """,
    )
    write_sql_test_file(
        test_file_path,
        (
            (
                """
                TEST ();

                WITH
                helper_orders AS (
                  SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
                ),
                __source__orders AS (
                  SELECT * FROM helper_orders
                ),
                expected_rows AS (
                  SELECT 'ord_001' AS order_id, {expected_line_total} AS line_total
                ),
                __expected__order_items AS (
                  SELECT * FROM expected_rows
                )
                SELECT 1
                """
            )
            if test_case.description
            not in {
                "runs multiple sql tests from one file",
                "renders grouped failures for multiple expected targets in one test",
            }
            else """
            TEST (name: "line total computes correctly");

            WITH
            helper_orders AS (
              SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
            ),
            __source__orders AS (
              SELECT * FROM helper_orders
            ),
            __expected__order_items AS (
              SELECT 'ord_001' AS order_id, 20.0 AS line_total
            )
            SELECT 1;

            TEST (name: "line total remains stable on repeat");

            WITH
            helper_orders AS (
              SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
            ),
            __source__orders AS (
              SELECT * FROM helper_orders
            ),
            __expected__order_items AS (
              SELECT 'ord_001' AS order_id, 20.0 AS line_total
            )
            SELECT 1
            """
            if test_case.description == "runs multiple sql tests from one file"
            else """
            TEST ();

            WITH
            helper_orders AS (
              SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
            ),
            __source__orders AS (
              SELECT * FROM helper_orders
            ),
            __expected__order_items AS (
              SELECT 'ord_001' AS order_id, 25.0 AS line_total
            ),
            __expected__daily_revenue AS (
              SELECT 'ord_001' AS order_id, 30.0 AS line_total
            )
            SELECT 1
            """
        ).format(expected_line_total="20.0" if test_case.expected_exit_code == 0 else "25.0"),
    )
    if test_case.description not in {
        "runs multiple sql tests from one file",
        "renders grouped failures for multiple expected targets in one test",
    }:
        write_sql_test_file(
            downstream_test_file_path,
            """
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
        )
    managed_client: ClickHouseClient = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )

    try:
        exit_code: int = run_test(
            tmp_path / "pipelines",
            project_dir=tmp_path,
            selectors=test_case.selectors,
            paths=(),
            verbose=False,
            client=managed_client,
        )
    finally:
        managed_client.close()
    captured: CaptureResult[str] = capsys.readouterr()

    assert clickhouse_client.query("SELECT 1").result_rows == [(1,)]
    assert exit_code == test_case.expected_exit_code
    expected_output_fragment: str
    for expected_output_fragment in test_case.expected_output_fragments:
        assert expected_output_fragment in captured.out
