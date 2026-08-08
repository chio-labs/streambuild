"""Validation for virtual-environment-only authored replay policies."""

from pathlib import Path

from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.models import LoadedPipeline, Project, TransformStep, ViewStep
from streambuild.compiler.discovery.types import PipelineMode


def validate_replay_policies_for_mode(
    *,
    default_pipeline_mode: PipelineMode,
    project: Project | None,
    project_file_path: Path | None,
    loaded_pipelines: tuple[LoadedPipeline, ...],
) -> None:
    """Reject change-driven policy at every authored level in direct mode."""

    has_virtual_pipeline: bool = any(
        loaded_pipeline.pipeline.mode == PipelineMode.VIRTUAL
        for loaded_pipeline in loaded_pipelines
    )
    no_virtual_mode_reason: str = (
        "defaults.pipeline_mode is direct"
        if default_pipeline_mode == PipelineMode.DIRECT
        else "every pipeline overrides its mode to direct"
    )
    if not has_virtual_pipeline and project is not None and project.replay_on_change is not None:
        raise PipelineDiscoveryError(
            f"Project file '{project_file_path}' cannot define defaults.replay_on_change "
            f"when {no_virtual_mode_reason}"
        )
    if (
        not has_virtual_pipeline
        and project is not None
        and project.bounded_replay_fallback is not None
    ):
        raise PipelineDiscoveryError(
            f"Project file '{project_file_path}' cannot define defaults.bounded_replay_fallback "
            f"when {no_virtual_mode_reason}"
        )
    loaded_pipeline: LoadedPipeline
    for loaded_pipeline in loaded_pipelines:
        if loaded_pipeline.pipeline.mode == PipelineMode.VIRTUAL:
            continue
        if loaded_pipeline.pipeline.replay_on_change is not None:
            raise PipelineDiscoveryError(
                f"Pipeline '{loaded_pipeline.file_path}' cannot define replay_on_change "
                "when its mode is direct"
            )
        if loaded_pipeline.pipeline.bounded_replay_fallback is not None:
            raise PipelineDiscoveryError(
                f"Pipeline '{loaded_pipeline.file_path}' cannot define "
                "bounded_replay_fallback when its mode is direct"
            )
        model: TransformStep | ViewStep
        for model in loaded_pipeline.pipeline.transforms:
            if not isinstance(model, TransformStep):
                continue
            transform: TransformStep = model
            if transform.replay_on_change is not None:
                raise PipelineDiscoveryError(
                    f"Model '{transform.name}' in '{loaded_pipeline.file_path}' cannot define "
                    "replay_on_change when its pipeline mode is direct"
                )
            if transform.bounded_replay_fallback is not None:
                raise PipelineDiscoveryError(
                    f"Model '{transform.name}' in '{loaded_pipeline.file_path}' cannot define "
                    "bounded_replay_fallback when its pipeline mode is direct"
                )
