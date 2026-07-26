"""Neutral adapter identity, connection, and result models."""

from collections.abc import Mapping
from dataclasses import dataclass

from streambuild.adapter.constants import REDACTED_SECRET_PLACEHOLDER
from streambuild.adapter.exceptions import AdapterResultError


@dataclass(frozen=True)
class AdapterIdentity:
    """The registered name of one adapter implementation."""

    name: str


@dataclass(frozen=True, repr=False)
class AdapterConnectionConfig:
    """Resolved, format-neutral connection settings for one adapter."""

    host: str
    port: int
    username: str
    password: str
    database: str | None = None

    def __repr__(self) -> str:
        """Render the configuration without exposing the password."""

        return (
            f"{type(self).__name__}(host={self.host!r}, port={self.port!r}, "
            f"username={self.username!r}, password={REDACTED_SECRET_PLACEHOLDER!r}, "
            f"database={self.database!r})"
        )


@dataclass(frozen=True)
class AdapterQueryResult:
    """A normalized query result returned by the adapter boundary."""

    rows: tuple[tuple[object, ...], ...]
    column_names: tuple[str, ...] = ()

    def named_rows(self) -> tuple[Mapping[str, object], ...]:
        """Return rows keyed by the query's column names."""

        if not self.column_names:
            if not self.rows:
                return ()
            raise AdapterResultError("Query result does not include column names")
        return tuple(dict(zip(self.column_names, row, strict=True)) for row in self.rows)
