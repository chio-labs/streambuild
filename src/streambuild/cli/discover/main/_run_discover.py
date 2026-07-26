"""CLI command for pipeline discovery."""

import json
from pathlib import Path

from streambuild.compiler.discovery.main.discover_pipelines import discover_pipelines
from streambuild.compiler.discovery.models import LoadedPipeline


def run_discover(pipelines_root: Path) -> int:
    """Run pipeline discovery for pipeline.yml-rooted folders and print names."""

    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
    print(json.dumps([pipeline.pipeline.name for pipeline in loaded_pipelines], indent=2))
    return 0
