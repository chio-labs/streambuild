"""Inspect live ClickHouse managed table state."""

from streambuild.clickhouse.inspect._helpers.managed_tables import (
    build_inspected_managed_table_state,
)
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def inspect_managed_table_state(
    *,
    client: ClickHouseClient,
    database: str,
) -> InspectedManagedTableState:
    """Inspect active logical bindings and deployment-suffixed physical tables."""

    return build_inspected_managed_table_state(client=client, database=database)
