"""Iterate every compiled transform across a set of compiled pipelines."""

from __future__ import annotations

from collections.abc import Iterator

from streambuild.compiler.compile.models import CompiledPipeline, CompiledTransformStep


def compiled_transforms(
    *, compiled_pipelines: tuple[CompiledPipeline, ...]
) -> Iterator[CompiledTransformStep]:
    """Yield each compiled transform, flattening the pipeline dimension.

    Callers repeatedly need every transform across every pipeline. Naming that
    traversal keeps their comprehensions single-generator.
    """

    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        yield from compiled_pipeline.transforms
