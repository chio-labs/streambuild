"""Models for assembled SQL-native test cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.compile.models import CompiledPipeline, CompiledTransformStep


@dataclass(frozen=True)
class SqlTestTargetCase:
    """One assembled target comparison inside a SQL-native test case."""

    target_model_name: str
    expected_column_names: tuple[str, ...]
    query: str


@dataclass(frozen=True)
class SqlTestCase:
    """One fully assembled SQL-native test scenario ready for execution."""

    file_path: Path
    target_cases: tuple[SqlTestTargetCase, ...]
    name: str | None = None
    test_index: int = 1


@dataclass(frozen=True)
class CompiledSqlTestModelEntry:
    """One compiled model entry used while assembling SQL test cases."""

    compiled_pipeline: CompiledPipeline
    compiled_transform: CompiledTransformStep
