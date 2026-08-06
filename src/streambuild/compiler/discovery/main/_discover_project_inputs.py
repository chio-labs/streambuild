"""Apache-2.0: SQLBuild compiler/discovery/main/discover.py@7e3b2f854f05."""

from pathlib import Path

from streambuild.compiler.discovery._helpers.project_inputs import (
    discover_pipeline_directories,
    read_discovered_files,
)
from streambuild.compiler.discovery.constants import PYTHON_PACKAGE_INITIALIZER_FILE_NAME
from streambuild.compiler.discovery.models import (
    DiscoveredPipelineDirectory,
    DiscoveredProjectFile,
    DiscoveredProjectInputs,
    DiscoveredSourceFile,
    LoadedProject,
)


def discover_project_inputs(
    *, pipelines_root: Path, loaded_project: LoadedProject | None
) -> DiscoveredProjectInputs:
    """Load all project source kinds once in stable path order, then validate the aggregate."""

    project_dir: Path = pipelines_root.parent
    pipeline_directories: tuple[DiscoveredPipelineDirectory, ...] = discover_pipeline_directories(
        pipelines_root=pipelines_root,
        project_dir=project_dir,
    )
    model_files: tuple[DiscoveredProjectFile, ...] = read_discovered_files(
        file_paths=tuple(pipelines_root.rglob("*.sql")),
        project_dir=project_dir,
    )
    test_files: tuple[DiscoveredProjectFile, ...] = read_discovered_files(
        file_paths=tuple((project_dir / "tests").rglob("*.sql")),
        project_dir=project_dir,
    )
    audit_files: tuple[DiscoveredProjectFile, ...] = read_discovered_files(
        file_paths=tuple((project_dir / "audits").rglob("*.sql")),
        project_dir=project_dir,
    )
    macro_files: tuple[DiscoveredProjectFile, ...] = read_discovered_files(
        file_paths=tuple(
            path
            for path in (project_dir / "macros").rglob("*.py")
            if _is_public_macro_file(path=path, project_dir=project_dir)
        ),
        project_dir=project_dir,
    )
    source_files: tuple[DiscoveredSourceFile, ...] = (
        () if loaded_project is None else loaded_project.source_files
    )
    return DiscoveredProjectInputs(
        project_dir=project_dir,
        loaded_project=loaded_project,
        source_files=source_files,
        pipeline_directories=pipeline_directories,
        model_files=model_files,
        test_files=test_files,
        audit_files=audit_files,
        macro_files=macro_files,
    )


def _is_public_macro_file(*, path: Path, project_dir: Path) -> bool:
    relative_path: Path = path.relative_to(project_dir)
    return path.name != PYTHON_PACKAGE_INITIALIZER_FILE_NAME and not any(
        part.startswith("_") for part in relative_path.parts
    )
