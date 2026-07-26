"""Janitor preview entrypoint."""

from streambuild.clickhouse.inspect.main import inspect_managed_table_state
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.executor.janitor._helpers.execute import execute_janitor_for_managed_table_state
from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewResult,
    JanitorRequest,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient


def execute_janitor(
    *,
    request: JanitorRequest,
    client: ClickHouseClient,
) -> JanitorPreviewResult | JanitorApplyResult:
    managed_table_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=request.database,
    )
    return execute_janitor_for_managed_table_state(
        request=request,
        client=client,
        managed_table_state=managed_table_state,
    )
