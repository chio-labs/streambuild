"""ClickHouse-backed implementation of the neutral connection contract."""

from __future__ import annotations

from collections.abc import Sequence

from clickhouse_connect.driver.exceptions import ClickHouseError, StreamFailureError

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterQueryResult
from streambuild.adapters.clickhouse._helpers.errors import translate_driver_error
from streambuild.adapters.clickhouse.types import (
    RawClickHouseClient,
    RawClickHouseQueryResult,
)


class ClickHouseConnection(AdapterConnection):
    """A neutral adapter connection backed by the ClickHouse driver."""

    def __init__(self, raw_client: RawClickHouseClient) -> None:
        self._raw_client: RawClickHouseClient = raw_client

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
