"""Compiler-side SQL test models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.quality.models import QualityNodeIdentity


@dataclass(frozen=True)
class SqlTestChainStep:
    """One recursively assembled actual/expected comparison."""

    target_model_name: str
    expected_column_names: tuple[str, ...]
    ctes: tuple[tuple[str, str], ...]
    actual_query: str
    expected_query: str


@dataclass(frozen=True)
class SqlTestAssertionStep:
    """One zero-row assertion assembled against the resolved test chain."""

    name: str
    column_names: tuple[str, ...]
    ctes: tuple[tuple[str, str], ...]
    query: str


@dataclass(frozen=True)
class SqlTestCase:
    """One fully assembled SQL-native test and its canonical adapter statement."""

    file_path: Path
    query: str
    target_cases: tuple[SqlTestChainStep, ...]
    assertion_cases: tuple[SqlTestAssertionStep, ...] = ()
    warnings: tuple[str, ...] = ()
    name: str | None = None
    test_index: int = 1
    quality_identity: QualityNodeIdentity | None = None
