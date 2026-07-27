"""Janitor preview entrypoint."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import InspectedManagedTableState
from streambuild.executor.janitor._helpers.execute import execute_janitor_for_managed_table_state
from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewResult,
    JanitorRequest,
)


def execute_janitor(
    *,
    request: JanitorRequest,
    client: AdapterConnection,
) -> JanitorPreviewResult | JanitorApplyResult:
    managed_table_state: InspectedManagedTableState = client.inspect_managed_table_state(
        request.database
    )
    return execute_janitor_for_managed_table_state(
        request=request,
        client=client,
        managed_table_state=managed_table_state,
    )
