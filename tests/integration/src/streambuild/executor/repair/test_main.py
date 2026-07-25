from collections.abc import Sequence

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.executor.repair.main import execute_repair_active_view
from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult
from streambuild.integrations.clickhouse.client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.repair._test_types import (
    ExecuteRepairActiveViewIntegrationTestCase,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteRepairActiveViewIntegrationTestCase(
            description="rebinds stable active view to chosen deployment table",
            deployment_id="dep_b",
            expected_target_table_name="tbl__orders_enriched__dep_b",
        )
    ],
    ids=["rebinds stable active view to chosen deployment table"],
)
def test_given_table_and_deployment_when_repairing_active_view_then_it_rebinds_the_view(
    test_case: ExecuteRepairActiveViewIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.tbl__orders_enriched__dep_a "
        "(order_id String) ENGINE = MergeTree ORDER BY (order_id)"
    )
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.tbl__orders_enriched__dep_b "
        "(order_id String) ENGINE = MergeTree ORDER BY (order_id)"
    )
    managed_client: ClickHouseClient = ClickHouseClient.from_config(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        result: RepairActiveViewResult = execute_repair_active_view(
            RepairActiveViewRequest(
                default_database=clickhouse_database,
                table_name="tbl__orders_enriched",
                deployment_id=test_case.deployment_id,
            ),
            managed_client,
        )
    finally:
        managed_client.close()

    view_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT as_select FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name = 'tbl__orders_enriched'"
    ).result_rows

    assert result.table_name == "tbl__orders_enriched"
    assert result.target_table_name == test_case.expected_target_table_name
    assert test_case.expected_target_table_name in str(view_rows[0][0])
