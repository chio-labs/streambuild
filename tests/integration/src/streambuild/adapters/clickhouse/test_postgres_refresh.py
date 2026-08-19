"""Apply refreshable materialized view DDL against a real ClickHouse server."""

from collections.abc import Sequence

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterColumn,
    AdapterMaterializedView,
    AdapterRefreshState,
    AdapterTable,
)
from streambuild.adapters.clickhouse._helpers.rendering import render_clickhouse_resource
from tests.integration.src.streambuild.adapters.clickhouse._test_types import (
    RefreshableViewIntegrationTestCase,
    RefreshStateIntegrationTestCase,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        RefreshableViewIntegrationTestCase(
            description="an hourly refreshable view is accepted and registered",
            refresh="1 HOUR",
            append=False,
            expected_row_count=1,
        ),
        RefreshableViewIntegrationTestCase(
            description="a ten minute refreshable view is accepted and registered",
            refresh="10 MINUTE",
            append=False,
            expected_row_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_refreshable_view_when_applied_to_real_clickhouse_then_it_registers_its_schedule(
    test_case: RefreshableViewIntegrationTestCase,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    target: AdapterTable = AdapterTable(
        name="pg__course",
        columns=(
            AdapterColumn(name="course_key", type="String"),
            AdapterColumn(name="refresh_ts", type="DateTime64(3)"),
        ),
        engine="ReplacingMergeTree(refresh_ts)",
        order_by=("course_key",),
    )
    query: str = "SELECT 'course-1' AS course_key, now64(3) AS refresh_ts"
    view: AdapterMaterializedView = AdapterMaterializedView(
        name="mv__pg__course",
        source_relation_name="unicron__course",
        target_relation_name=target.name,
        query=query,
        database_template=query,
        refresh=test_case.refresh,
        append=test_case.append,
    )

    clickhouse_client.command(
        render_clickhouse_resource(resource=target, database=clickhouse_database)
    )
    clickhouse_client.command(
        render_clickhouse_resource(resource=view, database=clickhouse_database)
    )

    registered: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT count() FROM system.view_refreshes "
        f"WHERE database = '{clickhouse_database}' AND view = '{view.name}'"
    ).result_rows

    assert int(str(registered[0][0])) == test_case.expected_row_count


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        RefreshStateIntegrationTestCase(
            description="a scheduled relation reports its refresh state",
            refresh="1 HOUR",
            expected_statuses=("Scheduled", "Running", "RunningOnAnotherReplica"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scheduled_relation_when_loading_refresh_states_then_status_is_reported(
    test_case: RefreshStateIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    target: AdapterTable = AdapterTable(
        name="pg__course",
        columns=(
            AdapterColumn(name="course_key", type="String"),
            AdapterColumn(name="refresh_ts", type="DateTime64(3)"),
        ),
        engine="ReplacingMergeTree(refresh_ts)",
        order_by=("course_key",),
    )
    query: str = "SELECT 'course-1' AS course_key, now64(3) AS refresh_ts"
    view: AdapterMaterializedView = AdapterMaterializedView(
        name="mv__pg__course",
        source_relation_name="unicron__course",
        target_relation_name=target.name,
        query=query,
        database_template=query,
        refresh=test_case.refresh,
        append=False,
    )
    clickhouse_client.command(
        render_clickhouse_resource(resource=target, database=clickhouse_database)
    )
    clickhouse_client.command(
        render_clickhouse_resource(resource=view, database=clickhouse_database)
    )

    states: tuple[AdapterRefreshState, ...] = managed_clickhouse_client.load_refresh_states(
        clickhouse_database
    )

    assert tuple(state.view_name for state in states) == (view.name,)
    assert states[0].status in test_case.expected_statuses
    assert states[0].exception is None
