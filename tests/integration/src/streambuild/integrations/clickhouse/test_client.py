import pytest

from streambuild.integrations.clickhouse.client import ClickHouseClient
from tests.integration.src.streambuild.integrations.clickhouse._test_types import (
    ClickHouseClientIntegrationTestCase,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseClientIntegrationTestCase(
            description="creates a real client and executes command insert query and close",
            inserted_rows=(
                {"deployment_id": "dep_1", "status": "open"},
                {"deployment_id": "dep_2", "status": "failed"},
            ),
            expected_rows=(("dep_1", "open"), ("dep_2", "failed")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_clickhouse_when_using_client_then_it_executes_expected_operations(
    test_case: ClickHouseClientIntegrationTestCase,
    managed_clickhouse_client: ClickHouseClient,
    clickhouse_database: str,
) -> None:
    managed_clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.deployments (deployment_id String, status String) "
        "ENGINE = MergeTree ORDER BY deployment_id"
    )

    managed_clickhouse_client.insert_rows(
        table=f"{clickhouse_database}.deployments",
        rows=test_case.inserted_rows,
    )

    result_rows: tuple[tuple[object, ...], ...] = managed_clickhouse_client.query(
        f"SELECT deployment_id, status FROM {clickhouse_database}.deployments "
        "ORDER BY deployment_id"
    ).rows

    assert result_rows == test_case.expected_rows
