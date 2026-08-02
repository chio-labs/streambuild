"""Type-only protocols for the wrapped ClickHouse driver."""

from collections.abc import Sequence
from typing import Protocol


class RawClickHouseQueryResult(Protocol):
    """Protocol for raw ClickHouse query results."""

    column_names: Sequence[str]
    result_rows: Sequence[Sequence[object]]


class RawClickHouseClient(Protocol):
    """Protocol for the wrapped ClickHouse driver client."""

    def command(self, statement: str) -> object: ...

    def query(self, statement: str) -> RawClickHouseQueryResult: ...

    def close(self) -> None: ...
