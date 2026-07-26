"""ClickHouse-backed implementation of the neutral connection contract."""

from __future__ import annotations

from collections.abc import Sequence

from clickhouse_connect.driver.exceptions import ClickHouseError, StreamFailureError

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterCapabilities,
    AdapterIdentity,
    AdapterQueryResult,
    CatalogSnapshot,
)
from streambuild.adapters.clickhouse._helpers.errors import translate_driver_error
from streambuild.adapters.clickhouse._helpers.inspection import load_clickhouse_catalog
from streambuild.adapters.clickhouse.constants import (
    CLICKHOUSE_ADAPTER_NAME,
    CLICKHOUSE_VIRTUAL_ENVIRONMENTS_SUPPORTED,
)
from streambuild.adapters.clickhouse.types import (
    RawClickHouseClient,
    RawClickHouseQueryResult,
)


class ClickHouseConnection(AdapterConnection):
    """A neutral adapter connection backed by the ClickHouse driver."""

    def __init__(self, raw_client: RawClickHouseClient) -> None:
        self._raw_client: RawClickHouseClient = raw_client

    @property
    def adapter_identity(self) -> AdapterIdentity:
        """Return the built-in ClickHouse adapter identity."""

        return AdapterIdentity(name=CLICKHOUSE_ADAPTER_NAME)

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Return capabilities implemented by the ClickHouse adapter."""

        return AdapterCapabilities(virtual_environments=CLICKHOUSE_VIRTUAL_ENVIRONMENTS_SUPPORTED)

    def load_catalog(self, database: str) -> CatalogSnapshot:
        """Load a neutral catalog snapshot from ClickHouse system tables."""

        return load_clickhouse_catalog(
            connection=self,
            adapter_identity=self.adapter_identity,
            database=database,
        )

    def command(self, statement: str) -> None:
        """Execute a ClickHouse command statement."""

        try:
            self._raw_client.command(statement)
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error

    def query(self, statement: str) -> AdapterQueryResult:
        """Execute a ClickHouse query and normalize the returned rows."""

        try:
            raw_result: RawClickHouseQueryResult = self._raw_client.query(statement)
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error
        result_rows: Sequence[Sequence[object]] = raw_result.result_rows
        return AdapterQueryResult(
            column_names=tuple(raw_result.column_names),
            rows=tuple(tuple(row) for row in result_rows),
        )

    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        """Insert row mappings into a ClickHouse table."""

        if not rows:
            return

        column_names: tuple[str, ...] = tuple(rows[0].keys())
        row_values: list[list[object]] = []
        row: dict[str, object]
        for row in rows:
            row_values.append([row[column_name] for column_name in column_names])
        try:
            self._raw_client.insert(table=table, data=row_values, column_names=list(column_names))
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error

    def close(self) -> None:
        """Close the underlying ClickHouse connection."""

        try:
            self._raw_client.close()
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error
