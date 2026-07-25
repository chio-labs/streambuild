"""Runtime models for SQL-native test execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SqlTestTargetExecutionResult:
    """One executed target comparison inside a SQL-native test scenario."""

    target_model_name: str
    passed: bool
    column_names: tuple[str, ...]
    missing_rows: tuple[tuple[object, ...], ...]
    unexpected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SqlTestExecutionResult:
    """One executed SQL test scenario and its aggregate diff outcome."""

    file_path: Path
    passed: bool
    target_results: tuple[SqlTestTargetExecutionResult, ...]
    name: str | None = None
    test_index: int = 1
