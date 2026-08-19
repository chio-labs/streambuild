"""Attach retained pipeline and model sources with one macro runtime."""

from collections.abc import Mapping

from streambuild.compiler.discovery._helpers.project_inputs import (
    load_discovered_pipelines as load_discovered_pipelines_impl,
)
from streambuild.compiler.discovery.models import (
    DiscoveredPipelineDirectory,
    DiscoveredProjectFile,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    PostgresRefreshSourceStep,
    Project,
    ProjectNaming,
)
from streambuild.compiler.discovery.types import PipelineMode
from streambuild.compiler.macros.models import MacroContext, MacroRegistry


def load_discovered_pipelines(
    *,
    pipeline_directories: tuple[DiscoveredPipelineDirectory, ...],
    model_files: tuple[DiscoveredProjectFile, ...],
    macro_registry: MacroRegistry,
    macro_context: MacroContext,
    sources_by_name: Mapping[
        str, KafkaLandingStep | ExternalTableSourceStep | PostgresRefreshSourceStep
    ],
    project: Project | None,
    project_naming: ProjectNaming,
    default_mode: PipelineMode,
) -> tuple[LoadedPipeline, ...]:
    """Attach retained pipeline/model sources without rereading or loading macros."""

    return load_discovered_pipelines_impl(
        pipeline_directories=pipeline_directories,
        model_files=model_files,
        macro_registry=macro_registry,
        macro_context=macro_context,
        sources_by_name=sources_by_name,
        project=project,
        project_naming=project_naming,
        default_mode=default_mode,
    )
