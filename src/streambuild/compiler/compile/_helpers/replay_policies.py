"""Compile-time replay boundary and policy resolution."""

from streambuild.compiler.compile.constants import LINEAGE_MODE_BY_REPLAY_BOUNDARY
from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.discovery.models import (
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    ReplayBoundary,
    ReplayOnChangePolicy,
    TransformStep,
)
from streambuild.compiler.discovery.types import BoundedReplayFallback, ReplayLineageMode


def resolve_replay_lineage_mode(*, loaded_pipeline: LoadedPipeline) -> ReplayLineageMode:
    """Resolve lineage from the selected source-owned physical replay contract."""

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
    if isinstance(loaded_pipeline.pipeline.source, KafkaLandingStep):
        replay_boundary: ReplayBoundary | None = loaded_pipeline.pipeline.source.replay_boundary
        if replay_boundary is not None:
            managed_lineage_mode: ReplayLineageMode | None = LINEAGE_MODE_BY_REPLAY_BOUNDARY.get(
                replay_boundary.mode
            )
            if managed_lineage_mode is not None:
                return managed_lineage_mode
    return ReplayLineageMode(ReplayLineageMode.OFFSETS)


def resolve_replay_on_change(
    *, loaded_pipeline: LoadedPipeline, transform: TransformStep
) -> ReplayOnChangePolicy | None:
    """Resolve model, pipeline, then project replay-on-change precedence."""

    if transform.replay_on_change is not None:
        return transform.replay_on_change
    if loaded_pipeline.pipeline.replay_on_change is not None:
        return loaded_pipeline.pipeline.replay_on_change
    if loaded_pipeline.project is not None:
        return loaded_pipeline.project.replay_on_change
    return None


def resolve_bounded_replay_fallback(
    *, loaded_pipeline: LoadedPipeline, transform: TransformStep
) -> BoundedReplayFallback:
    """Resolve model, pipeline, then project bounded-replay fallback precedence."""

    if transform.bounded_replay_fallback is not None:
        return BoundedReplayFallback(transform.bounded_replay_fallback)
    if loaded_pipeline.pipeline.bounded_replay_fallback is not None:
        return BoundedReplayFallback(loaded_pipeline.pipeline.bounded_replay_fallback)
    if (
        loaded_pipeline.project is not None
        and loaded_pipeline.project.bounded_replay_fallback is not None
    ):
        return BoundedReplayFallback(loaded_pipeline.project.bounded_replay_fallback)
    return BoundedReplayFallback(BoundedReplayFallback.FULL)
