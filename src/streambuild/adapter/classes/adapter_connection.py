"""Neutral warehouse connection contract."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping

from streambuild.adapter.models import AdapterQueryResult


class AdapterConnection(ABC):
    """An open warehouse connection exposing neutral statements and results."""

    @abstractmethod
    def command(self, statement: str) -> None:
        """Execute a statement that returns no result rows."""

    @abstractmethod
    def query(self, statement: str) -> AdapterQueryResult:
        """Execute a query and return its normalized result."""

    @abstractmethod
    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        """Insert row mappings into a warehouse table."""

    @abstractmethod
    def close(self) -> None:
        """Close the underlying connection."""

    def query_many[DecodedRow](
        self,
        *,
        statement: str,
        decode: Callable[[Mapping[str, object]], DecodedRow],
    ) -> tuple[DecodedRow, ...]:
        """Execute a query and decode every row into a typed object."""

        result: AdapterQueryResult = self.query(statement)
        return tuple(decode(row) for row in result.named_rows())

    def query_one[DecodedRow](
        self,
        *,
        statement: str,
        decode: Callable[[Mapping[str, object]], DecodedRow],
    ) -> DecodedRow | None:
        """Execute a query and decode the first row if one exists."""

        rows: tuple[DecodedRow, ...] = self.query_many(statement=statement, decode=decode)
        return rows[0] if rows else None
