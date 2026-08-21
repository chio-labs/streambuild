"""Type-only protocols for the wrapped ClickHouse driver."""

from collections.abc import Mapping, Sequence
from typing import Protocol


class RawClickHouseQueryResult(Protocol):
    """Protocol for raw ClickHouse query results."""

    column_names: Sequence[str]
    result_rows: Sequence[Sequence[object]]


class RawClickHouseClient(Protocol):
    """Protocol for the wrapped ClickHouse driver client."""

    def command(self, *, cmd: str, settings: Mapping[str, str] | None = None) -> object: ...

    def query(
        self, *, query: str, settings: Mapping[str, str] | None = None
    ) -> RawClickHouseQueryResult: ...

    def close(self) -> None: ...
