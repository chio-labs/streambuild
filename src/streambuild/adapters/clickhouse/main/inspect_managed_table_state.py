"""Inspect live ClickHouse managed table state."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import InspectedManagedTableState
from streambuild.adapters.clickhouse._helpers.managed_tables import (
    build_inspected_managed_table_state,
)


def inspect_managed_table_state(
    *,
    client: AdapterConnection,
    database: str,
) -> InspectedManagedTableState:
    """Inspect active logical bindings and deployment-suffixed physical tables."""

    return build_inspected_managed_table_state(client=client, database=database)
