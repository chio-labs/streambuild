"""Models for assembled SQL-native test cases."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.compile.models import CompiledModel, CompiledPipeline


@dataclass(frozen=True)
class CompiledSqlTestModelEntry:
    """One compiled model entry used while assembling SQL test cases."""

    compiled_pipeline: CompiledPipeline
    compiled_model: CompiledModel
