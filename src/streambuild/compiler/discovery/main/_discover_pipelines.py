"""Filesystem discovery for authored pipeline folders."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.discovery._helpers.load import (
    load_pipeline_yaml,
    updated_unique_logical_names,
)
from streambuild.compiler.discovery._helpers.source_registry import source_registry_by_name
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import (
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    LoadedProject,
)


def discover_pipelines(root: Path) -> list[LoadedPipeline]:
    """Load all pipeline roots under a pipelines root directory."""

    loaded_pipelines: list[LoadedPipeline] = []
    logical_node_names: dict[str, Path] = {}
    loaded_project: LoadedProject | None = load_project_input_for_path(path=root)
    if loaded_project is None:
        return []
    sources_by_name: dict[str, KafkaLandingStep | ExternalTableSourceStep] = (
        source_registry_by_name(loaded_project.source_files)
    )
    file_path: Path
    for file_path in sorted(root.rglob("pipeline.yml")):
        loaded_pipeline: LoadedPipeline = LoadedPipeline(
            pipeline=load_pipeline_yaml(
                file_path=file_path,
                sources_by_name=sources_by_name,
            ),
            file_path=file_path,
            project=loaded_project.project,
        )
        logical_node_names = updated_unique_logical_names(
            loaded_pipeline=loaded_pipeline, logical_node_names=logical_node_names
        )
        loaded_pipelines.append(loaded_pipeline)
    return loaded_pipelines
