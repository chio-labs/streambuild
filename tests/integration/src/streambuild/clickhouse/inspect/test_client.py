import pytest
from clickhouse_connect.driver.client import Client

from streambuild.clickhouse.inspect.main import inspect_managed_table_state
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.clickhouse.render.helpers.create_view.main import render_create_view_ddl
from streambuild.integrations.clickhouse.client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from tests.integration.src.streambuild.clickhouse.inspect._test_types import (
    InspectManagedTableStateIntegrationTestCase,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        InspectManagedTableStateIntegrationTestCase(
            description="inspects stable view bindings and physical deployment candidates",
            expected_active_bindings=(("tbl__orders_enriched", "tbl__orders_enriched__dep_a"),),
            expected_physical_candidates=(
                ("tbl__orders_enriched", "tbl__orders_enriched__dep_a"),
                ("tbl__orders_enriched", "tbl__orders_enriched__dep_b"),
            ),
        )
    ],
    ids=["inspects stable view bindings and physical deployment candidates"],
)
def test_given_views_and_physical_tables_when_inspecting_then_it_returns_expected_state(
    test_case: InspectManagedTableStateIntegrationTestCase,
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
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__orders_enriched",
            target_table_name="tbl__orders_enriched__dep_a",
        )
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
        inspected_state: InspectedManagedTableState = inspect_managed_table_state(
            client=managed_client,
            database=clickhouse_database,
        )
    finally:
        managed_client.close()

    assert (
        tuple(
            (binding.logical_name, binding.physical_name)
            for binding in inspected_state.active_bindings
        )
        == test_case.expected_active_bindings
    )
    assert (
        tuple(
            (candidate.logical_name, candidate.physical_name)
            for candidate in inspected_state.physical_candidates
        )
        == test_case.expected_physical_candidates
    )
