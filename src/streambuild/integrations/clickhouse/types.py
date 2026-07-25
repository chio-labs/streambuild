"""Type-only ClickHouse client protocols."""

from collections.abc import Sequence
from typing import Protocol


class RawClickHouseQueryResult(Protocol):
    """Protocol for raw ClickHouse query results."""

    column_names: Sequence[str]
    result_rows: Sequence[Sequence[object]]


class RawClickHouseClient(Protocol):
    """Protocol for the wrapped ClickHouse client."""

    def command(self, statement: str) -> None: ...

    def query(self, statement: str) -> RawClickHouseQueryResult: ...

    def insert(self, table: str, rows: list[list[object]], column_names: list[str]) -> None: ...

    def close(self) -> None: ...
