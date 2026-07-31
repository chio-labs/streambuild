"""Filesystem discovery for authored pipeline folders."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.discovery._helpers.load import load_pipeline_directories
from streambuild.compiler.discovery._helpers.project_inputs import (
    discover_pipeline_directories,
)
from streambuild.compiler.discovery._helpers.source_registry import source_registry_by_name
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import (
    DiscoveredPipelineDirectory,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    LoadedProject,
    Pipeline,
)


def discover_pipelines(root: Path) -> list[LoadedPipeline]:
    """Load all pipeline roots under a pipelines root directory."""

    loaded_project: LoadedProject | None = load_project_input_for_path(path=root)
    if loaded_project is None:
        return []
    sources_by_name: dict[str, KafkaLandingStep | ExternalTableSourceStep] = (
        source_registry_by_name(loaded_project.source_files)
    )
    pipeline_directories: tuple[DiscoveredPipelineDirectory, ...] = discover_pipeline_directories(
        pipelines_root=root,
        project_dir=root.parent,
    )
    pipelines: tuple[Pipeline, ...] = load_pipeline_directories(
        pipeline_directories=pipeline_directories,
        sources_by_name=sources_by_name,
    )
    return [
        LoadedPipeline(
            pipeline=pipeline,
            file_path=pipeline_directory.pipeline_dir,
            project=loaded_project.project,
        )
        for pipeline_directory, pipeline in zip(pipeline_directories, pipelines, strict=True)
    ]
