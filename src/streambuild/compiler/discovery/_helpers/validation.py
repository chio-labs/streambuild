"""Apache-2.0: SQLBuild compiler/discovery/_helpers/filesystem/aggregation.py@7e3b2f854f05."""

from pathlib import Path

from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.discovery._helpers.replay_policy_validation import (
    validate_replay_policies_for_mode,
)
from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.models import (
    DiscoveredSourceFile,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    LoadedProject,
)
from streambuild.compiler.discovery.types import PipelineMode
from streambuild.compiler.test_discovery.models import LoadedSqlTest


def validate_discovered_project_inputs(
    *,
    source_files: tuple[DiscoveredSourceFile, ...],
    loaded_project: LoadedProject | None,
    loaded_pipelines: tuple[LoadedPipeline, ...],
    loaded_tests: tuple[LoadedSqlTest, ...],
    loaded_audits: tuple[LoadedSqlAudit, ...],
) -> None:
    """Reject duplicate project identities after semantic inputs are attached."""

    _validate_pipeline_names(loaded_pipelines)
    validate_replay_policies_for_mode(
        default_pipeline_mode=(
            PipelineMode.DIRECT
            if loaded_project is None or loaded_project.effective_configuration is None
            else PipelineMode(loaded_project.effective_configuration.defaults.pipeline_mode)
        ),
        project=None if loaded_project is None else loaded_project.project,
        project_file_path=None if loaded_project is None else loaded_project.source_file.file_path,
        loaded_pipelines=loaded_pipelines,
    )
    _validate_logical_node_names(
        logical_node_names=_source_logical_names(source_files),
        loaded_pipelines=loaded_pipelines,
    )
    _validate_test_names(loaded_tests)
    _validate_audit_names(loaded_audits)


def _source_logical_names(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> dict[str, Path]:
    logical_node_names: dict[str, Path] = {}
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source: KafkaLandingStep | ExternalTableSourceStep
        for source in source_file.sources:
            logical_node_names[source.name] = source_file.source_file.file_path
    return logical_node_names


def _validate_logical_node_names(
    *, logical_node_names: dict[str, Path], loaded_pipelines: tuple[LoadedPipeline, ...]
) -> None:
    known_logical_node_names: dict[str, Path] = dict(logical_node_names)
    loaded_pipeline: LoadedPipeline
    for loaded_pipeline in loaded_pipelines:
        logical_name: str
        for logical_name in (transform.name for transform in loaded_pipeline.pipeline.transforms):
            existing_path: Path | None = known_logical_node_names.get(logical_name)
            if existing_path is not None:
                raise PipelineDiscoveryError(
                    f"Logical node name '{logical_name}' is defined in both "
                    f"'{existing_path}' and '{loaded_pipeline.file_path}'"
                )
            known_logical_node_names[logical_name] = loaded_pipeline.file_path


def _validate_pipeline_names(loaded_pipelines: tuple[LoadedPipeline, ...]) -> None:
    names_and_paths: tuple[tuple[str, Path], ...] = tuple(
        (loaded_pipeline.pipeline.name, loaded_pipeline.file_path)
        for loaded_pipeline in loaded_pipelines
    )
    _validate_unique_names(resource_kind="pipeline", names_and_paths=names_and_paths)


def _validate_test_names(loaded_tests: tuple[LoadedSqlTest, ...]) -> None:
    names_and_paths: tuple[tuple[str, Path], ...] = tuple(
        (
            loaded_test.name if loaded_test.name is not None else loaded_test.file_path.stem,
            loaded_test.file_path,
        )
        for loaded_test in loaded_tests
    )
    _validate_unique_names(resource_kind="SQL test", names_and_paths=names_and_paths)


def _validate_audit_names(loaded_audits: tuple[LoadedSqlAudit, ...]) -> None:
    names_and_paths: tuple[tuple[str, Path], ...] = tuple(
        (
            loaded_audit.name if loaded_audit.name is not None else loaded_audit.file_path.stem,
            loaded_audit.file_path,
        )
        for loaded_audit in loaded_audits
    )
    _validate_unique_names(resource_kind="SQL audit", names_and_paths=names_and_paths)


def _validate_unique_names(
    *, resource_kind: str, names_and_paths: tuple[tuple[str, Path], ...]
) -> None:
    path_by_name: dict[str, Path] = {}
    name: str
    path: Path
    for name, path in names_and_paths:
        existing_path: Path | None = path_by_name.get(name)
        if existing_path is not None:
            raise PipelineDiscoveryError(
                f"Duplicate {resource_kind} name '{name}' found in '{existing_path}' and '{path}'"
            )
        path_by_name[name] = path
