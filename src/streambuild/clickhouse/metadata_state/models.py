"""Rendered ClickHouse metadata-state statements."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedClickHouseStatement:
    """A ClickHouse SQL statement plus row payloads when applicable."""

    sql: str
    rows: tuple[dict[str, object], ...] = ()
