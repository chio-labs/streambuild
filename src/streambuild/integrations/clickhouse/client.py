"""ClickHouse client boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import cast

import clickhouse_connect

from streambuild.integrations.clickhouse.models import (
    ClickHouseConnectionConfig,
    ClickHouseQueryResult,
)
from streambuild.integrations.clickhouse.types import RawClickHouseClient, RawClickHouseQueryResult


class ClickHouseClient:
    """Thin wrapper over the underlying ClickHouse client library."""

    def __init__(self, raw_client: RawClickHouseClient) -> None:
        self._raw_client: RawClickHouseClient = raw_client

    @classmethod
    def from_config(cls, config: ClickHouseConnectionConfig) -> ClickHouseClient:
        """Create a ClickHouse client wrapper from connection config."""

        if config.database is None:
            raw_client: RawClickHouseClient = cast(
                RawClickHouseClient,
                clickhouse_connect.get_client(
                    host=config.host,
                    port=config.port,
                    username=config.username,
                    password=config.password,
                ),
            )
        else:
            raw_client = cast(
                RawClickHouseClient,
                clickhouse_connect.get_client(
                    host=config.host,
                    port=config.port,
                    username=config.username,
                    password=config.password,
                    database=config.database,
                ),
            )
        return cls(raw_client)

    def command(self, statement: str) -> None:
        """Execute a ClickHouse command statement."""

        self._raw_client.command(statement)

    def query(self, statement: str) -> ClickHouseQueryResult:
        """Execute a ClickHouse query and normalize the returned rows."""

        raw_result: RawClickHouseQueryResult = self._raw_client.query(statement)
        result_rows: Sequence[Sequence[object]] = raw_result.result_rows
        return ClickHouseQueryResult(
            column_names=tuple(raw_result.column_names),
            rows=tuple(tuple(row) for row in result_rows),
        )

    def query_many[DecodedRow](
        self,
        *,
        statement: str,
        decode: Callable[[Mapping[str, object]], DecodedRow],
    ) -> tuple[DecodedRow, ...]:
        """Execute a query and decode all rows into typed objects."""

        result: ClickHouseQueryResult = self.query(statement)
        return tuple(decode(row) for row in result.named_rows())

    def query_one[DecodedRow](
        self,
        *,
        statement: str,
        decode: Callable[[Mapping[str, object]], DecodedRow],
    ) -> DecodedRow | None:
        """Execute a query and decode the first row if present."""

        rows: tuple[DecodedRow, ...] = self.query_many(statement=statement, decode=decode)
        return rows[0] if rows else None

    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        """Insert row dictionaries into a ClickHouse table."""

        if not rows:
            return

        column_names: tuple[str, ...] = tuple(rows[0].keys())
        row_values: list[list[object]] = [
            [row[column_name] for column_name in column_names] for row in rows
        ]
        self._raw_client.insert(table=table, data=row_values, column_names=list(column_names))

    def close(self) -> None:
        """Close the underlying client connection."""

        self._raw_client.close()
