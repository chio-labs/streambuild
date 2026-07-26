"""Create the StreamBuild metadata tables when they do not yet exist."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.clickhouse.metadata_state.main.render_metadata_state_statements import (
    render_metadata_state_statements,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement
from streambuild.executor.backfill._helpers.metadata import (
    ensure_database_exists,
)


def ensure_metadata_tables(*, client: AdapterConnection, metadata_database: str) -> None:
    """Create metadata state tables required for backfill bootstrap."""

    ensure_database_exists(client=client, database=metadata_database)
    statements: tuple[RenderedClickHouseStatement, ...] = render_metadata_state_statements(
        metadata_database
    )
    statement: RenderedClickHouseStatement
    for statement in statements:
        client.command(statement.sql)
