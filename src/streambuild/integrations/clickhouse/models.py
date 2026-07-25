"""ClickHouse integration models."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ClickHouseConnectionConfig:
    """Connection settings for a ClickHouse client."""

    host: str
    port: int
    username: str
    password: str
    database: str | None = None


@dataclass(frozen=True)
class ClickHouseQueryResult:
    """A normalized query result from the ClickHouse client boundary."""

    rows: tuple[tuple[object, ...], ...]
    column_names: tuple[str, ...] = ()

    def named_rows(self) -> tuple[Mapping[str, object], ...]:
        """Return rows keyed by the query's column names."""

        if not self.column_names:
            if not self.rows:
                return ()
            raise ValueError("Query result does not include column names")
        return tuple(dict(zip(self.column_names, row, strict=True)) for row in self.rows)
