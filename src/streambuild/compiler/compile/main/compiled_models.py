"""Iterate every compiled model across a set of compiled pipelines."""

from __future__ import annotations

from collections.abc import Iterator

from streambuild.compiler.compile.models import CompiledModel, CompiledPipeline


def compiled_models(*, compiled_pipelines: tuple[CompiledPipeline, ...]) -> Iterator[CompiledModel]:
    """Yield each compiled model, flattening the pipeline dimension."""

    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        yield from compiled_pipeline.models
