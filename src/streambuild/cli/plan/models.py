"""CLI plan models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompactChangedTargetSummary:
    target_name: str
    detail_lines: tuple[str, ...]
