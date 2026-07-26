"""Compilation entry points for desired state generation."""

from __future__ import annotations

from streambuild.compiler.compile._helpers.landing import (
    compile_external_source,
    compile_kafka_landing,
)
from streambuild.compiler.compile._helpers.transforms import (
    compile_transform,
    relation_names_for_pipeline,
    relation_sqls_for_pipeline,
)
from streambuild.compiler.compile.constants import LINEAGE_MODE_BY_REPLAY_BOUNDARY
from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledManagedSource,
    CompiledPipeline,
    CompiledTransformStep,
)
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.spec.models import ExternalTableSourceStep, Pipeline, Project, TransformStep
from streambuild.spec.types import BoundedReplayFallback, ReplayLineageMode


def compile_pipeline(loaded_pipeline: LoadedPipeline) -> CompiledPipeline:
    """Compile an authored pipeline into a minimal desired state representation."""

    pipeline: Pipeline = loaded_pipeline.pipeline
    project: Project | None = loaded_pipeline.project
    relation_names: dict[str, str] = relation_names_for_pipeline(pipeline)
    relation_sqls: dict[str, str] = relation_sqls_for_pipeline(pipeline)
    replay_lineage_mode: ReplayLineageMode = _resolve_replay_lineage_mode(
        loaded_pipeline=loaded_pipeline
    )
    compiled_source: CompiledManagedSource | CompiledExternalSource
    if isinstance(pipeline.source, ExternalTableSourceStep):
        compiled_source = compile_external_source(pipeline)
    else:
        compiled_source = compile_kafka_landing(pipeline)
    compiled_transforms: tuple[CompiledTransformStep, ...] = tuple(
        compile_transform(
            transform=transform,
            pipeline_file_path=loaded_pipeline.file_path,
            relation_names=relation_names,
            relation_sqls=relation_sqls,
            replay_lineage_mode=replay_lineage_mode,
            bounded_replay_fallback=_resolve_bounded_replay_fallback(
                loaded_pipeline=loaded_pipeline, transform=transform
            ),
        )
        for transform in pipeline.transforms
    )
    return CompiledPipeline(
        pipeline=pipeline,
        project=project,
        file_path=loaded_pipeline.file_path,
        relation_names=relation_names,
        relation_sqls=relation_sqls,
        effective_replay_lineage_mode=replay_lineage_mode,
        source=compiled_source,
        transforms=compiled_transforms,
    )


def _resolve_replay_lineage_mode(*, loaded_pipeline: LoadedPipeline) -> ReplayLineageMode:
    """Resolve the effective replay-lineage mode for a loaded pipeline.

    ReplayBoundary coerces its mode on construction, so an unknown boundary mode
    already fails in the spec layer and cannot reach the guard below.
    """

    if loaded_pipeline.pipeline.replay_lineage_mode is not None:
        return ReplayLineageMode(loaded_pipeline.pipeline.replay_lineage_mode)
    if isinstance(loaded_pipeline.pipeline.source, ExternalTableSourceStep):
        lineage_mode: ReplayLineageMode | None = LINEAGE_MODE_BY_REPLAY_BOUNDARY.get(
            loaded_pipeline.pipeline.source.replay_boundary.mode
        )
        if lineage_mode is not None:
            return lineage_mode
        raise PipelineCompileError(
            "External source replay boundary mode '"
            f"{loaded_pipeline.pipeline.source.replay_boundary.mode}"
            "' is not supported by compile/backfill"
        )
    if loaded_pipeline.project is not None:
        return ReplayLineageMode(loaded_pipeline.project.replay_lineage_mode)
    return ReplayLineageMode(ReplayLineageMode.OFFSETS)


def _resolve_bounded_replay_fallback(
    *,
    loaded_pipeline: LoadedPipeline,
    transform: TransformStep,
) -> BoundedReplayFallback:
    if transform.bounded_replay_fallback is not None:
        return BoundedReplayFallback(transform.bounded_replay_fallback)
    if loaded_pipeline.pipeline.bounded_replay_fallback is not None:
        return BoundedReplayFallback(loaded_pipeline.pipeline.bounded_replay_fallback)
    if loaded_pipeline.project is not None:
        return BoundedReplayFallback(loaded_pipeline.project.bounded_replay_fallback)
    return BoundedReplayFallback(BoundedReplayFallback.FULL_REFRESH)
