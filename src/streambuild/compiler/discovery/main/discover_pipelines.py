"""Filesystem discovery for authored pipeline folders."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.discovery._helpers.load import (
    load_pipeline_file,
    validate_unique_logical_names,
)
from streambuild.compiler.discovery.models import LoadedPipeline


def discover_pipelines(root: Path) -> list[LoadedPipeline]:
    """Load all pipeline roots under a pipelines root directory."""

    loaded_pipelines: list[LoadedPipeline] = []
    logical_node_names: dict[str, Path] = {}
    file_path: Path
    for file_path in sorted(root.rglob("pipeline.yml")):
        loaded_pipeline: LoadedPipeline = load_pipeline_file(file_path)
        validate_unique_logical_names(
            loaded_pipeline=loaded_pipeline, logical_node_names=logical_node_names
        )
        loaded_pipelines.append(loaded_pipeline)
    return loaded_pipelines
