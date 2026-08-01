"""Validation for virtual-environment-only authored replay policies."""

from pathlib import Path

from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.models import LoadedPipeline, Project, TransformStep, ViewStep


def validate_replay_policies_for_mode(
    *,
    virtual_environments: bool,
    project: Project | None,
    project_file_path: Path | None,
    loaded_pipelines: tuple[LoadedPipeline, ...],
) -> None:
    """Reject change-driven policy at every authored level in direct mode."""

    if virtual_environments:
        return
    if project is not None and project.replay_on_change is not None:
        raise PipelineDiscoveryError(
            f"Project file '{project_file_path}' cannot define defaults.replay_on_change "
            "when settings.virtual_environments is false"
        )
    if project is not None and project.bounded_replay_fallback is not None:
        raise PipelineDiscoveryError(
            f"Project file '{project_file_path}' cannot define defaults.bounded_replay_fallback "
            "when settings.virtual_environments is false"
        )
    loaded_pipeline: LoadedPipeline
    for loaded_pipeline in loaded_pipelines:
        if loaded_pipeline.pipeline.replay_on_change is not None:
            raise PipelineDiscoveryError(
                f"Pipeline '{loaded_pipeline.file_path}' cannot define replay_on_change "
                "when settings.virtual_environments is false"
            )
        if loaded_pipeline.pipeline.bounded_replay_fallback is not None:
            raise PipelineDiscoveryError(
                f"Pipeline '{loaded_pipeline.file_path}' cannot define "
                "bounded_replay_fallback when settings.virtual_environments is false"
            )
        model: TransformStep | ViewStep
        for model in loaded_pipeline.pipeline.transforms:
            if not isinstance(model, TransformStep):
                continue
            transform: TransformStep = model
            if transform.replay_on_change is not None:
                raise PipelineDiscoveryError(
                    f"Model '{transform.name}' in '{loaded_pipeline.file_path}' cannot define "
                    "replay_on_change when settings.virtual_environments is false"
                )
            if transform.bounded_replay_fallback is not None:
                raise PipelineDiscoveryError(
                    f"Model '{transform.name}' in '{loaded_pipeline.file_path}' cannot define "
                    "bounded_replay_fallback when settings.virtual_environments is false"
                )
