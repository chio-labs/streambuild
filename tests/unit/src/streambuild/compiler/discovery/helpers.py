from pathlib import Path
from textwrap import dedent

from streambuild.compiler.discovery.models import (
    DiscoveredSourceFile,
    ExternalTableSourceStep,
    KafkaLandingStep,
)


def write_project_toml(*, project_dir: Path, contents: str) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "streambuild_project.toml").write_text(
        dedent(contents).strip() + "\n",
        encoding="utf-8",
    )


def write_local_toml(*, project_dir: Path, contents: str) -> None:
    (project_dir / "streambuild_local.toml").write_text(
        dedent(contents).strip() + "\n",
        encoding="utf-8",
    )


def write_legacy_project_yaml(*, project_dir: Path) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "streambuild_project.yml").write_text("{}\n", encoding="utf-8")


def write_source_yml(*, project_dir: Path, relative_path: str, contents: str) -> None:
    file_path: Path = project_dir / "sources" / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")


def flatten_source_registry(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> tuple[KafkaLandingStep | ExternalTableSourceStep, ...]:
    sources: list[KafkaLandingStep | ExternalTableSourceStep] = []
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        sources.extend(source_file.sources)
    return tuple(sources)
