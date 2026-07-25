"""Runtime models for SQL-native test CLI rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PairedDiffSection:
    """One rendered diff section for SQL-native test output."""

    title: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    paired_row_count: int
