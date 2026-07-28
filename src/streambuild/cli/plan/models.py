"""CLI plan models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompactChangedTargetSummary:
    target_name: str
    detail_lines: tuple[str, ...]


@dataclass(frozen=True)
class PlanCommandOptions:
    """One resolved `stb plan` invocation independent of effective mode."""

    database: str
    selectors: tuple[str, ...]
    full_refresh: bool
    start_time: str | None
    json_output: bool
    verbose: bool
