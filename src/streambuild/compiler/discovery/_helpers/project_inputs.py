"""Apache-2.0: SQLBuild compiler/discovery/_helpers/filesystem/aggregation.py@7e3b2f854f05."""

from collections.abc import Mapping
from pathlib import Path

from streambuild.compiler.discovery._helpers.load import load_pipeline_yaml
from streambuild.compiler.discovery.models import (
    DiscoveredProjectFile,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    Project,
)
from streambuild.compiler.macros.models import MacroContext, MacroRegistry


def read_discovered_files(
    *, file_paths: tuple[Path, ...], project_dir: Path
) -> tuple[DiscoveredProjectFile, ...]:
    """Read sorted project paths into immutable source snapshots."""

    return tuple(
        DiscoveredProjectFile(
            file_path=file_path,
            relative_path=file_path.relative_to(project_dir),
            contents=file_path.read_text(encoding="utf-8"),
        )
        for file_path in sorted(file_paths)
    )


def load_discovered_pipelines(
    *,
    pipeline_files: tuple[DiscoveredProjectFile, ...],
    model_files: tuple[DiscoveredProjectFile, ...],
    macro_registry: MacroRegistry,
    macro_context: MacroContext,
    sources_by_name: Mapping[str, KafkaLandingStep | ExternalTableSourceStep],
    project: Project | None,
) -> tuple[LoadedPipeline, ...]:
    """Parse loaded pipeline and model sources without rereading either kind."""

    model_contents_by_path: dict[Path, str] = {
        model_file.file_path: model_file.contents for model_file in model_files
    }
    return tuple(
        LoadedPipeline(
            pipeline=load_pipeline_yaml(
                file_path=pipeline_file.file_path,
                contents=pipeline_file.contents,
                model_contents_by_path=model_contents_by_path,
                macro_registry=macro_registry,
                macro_context=macro_context,
                sources_by_name=sources_by_name,
            ),
            file_path=pipeline_file.file_path,
            project=project,
        )
        for pipeline_file in pipeline_files
    )
