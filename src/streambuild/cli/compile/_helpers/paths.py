"""Central path contract for static and runtime target artifacts."""

from pathlib import Path

from streambuild.cli.compile.constants import (
    ARTIFACT_PATH_SEPARATORS,
    UNSAFE_ARTIFACT_PATH_SEGMENTS,
)
from streambuild.cli.compile.exceptions import CompileArtifactError
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.test_discovery.models import SqlTestCase


def model_query_path(*, pipeline_name: str, model_name: str) -> Path:
    return Path(
        "compiled",
        "models",
        _safe_segment(value=pipeline_name, kind="pipeline"),
        f"{_safe_segment(value=model_name, kind='model')}.sql",
    )


def source_resource_path(*, source_name: str, resource_name: str) -> Path:
    return Path(
        "compiled",
        "resources",
        "sources",
        _safe_segment(value=source_name, kind="source"),
        f"{_safe_segment(value=resource_name, kind='adapter resource')}.sql",
    )


def model_table_path(*, pipeline_name: str, model_name: str) -> Path:
    return Path(
        "compiled",
        "resources",
        "models",
        _safe_segment(value=pipeline_name, kind="pipeline"),
        f"{_safe_segment(value=model_name, kind='model')}.table.sql",
    )


def model_view_path(*, pipeline_name: str, model_name: str) -> Path:
    return Path(
        "compiled",
        "resources",
        "models",
        _safe_segment(value=pipeline_name, kind="pipeline"),
        f"{_safe_segment(value=model_name, kind='model')}.mv.sql",
    )


def workflow_sql_path(*, pipeline_name: str) -> Path:
    return Path(
        "compiled",
        "workflows",
        _safe_segment(value=pipeline_name, kind="pipeline"),
        "workflow.sql",
    )


def workflow_json_path(*, pipeline_name: str) -> Path:
    return Path(
        "compiled",
        "workflows",
        _safe_segment(value=pipeline_name, kind="pipeline"),
        "workflow.json",
    )


def workflow_step_path(*, pipeline_name: str, step_name: str) -> Path:
    return Path(
        "compiled",
        "workflows",
        _safe_segment(value=pipeline_name, kind="pipeline"),
        "steps",
        _safe_segment(value=step_name, kind="workflow step"),
    )


def audit_path(*, audit: LoadedSqlAudit, project_dir: Path) -> Path:
    relative_file_path: Path = _audit_relative_path(
        file_path=audit.file_path,
        project_dir=project_dir,
    )
    suffix: str = "" if audit.name is None else f"__{_safe_segment(value=audit.name, kind='audit')}"
    return Path(
        "compiled",
        "audits",
        relative_file_path.parent,
        f"{_safe_segment(value=relative_file_path.stem, kind='audit file')}{suffix}.sql",
    )


def static_test_path(*, test_case: SqlTestCase) -> Path:
    test_name: str = _safe_segment(
        value=test_case.name or test_case.file_path.stem,
        kind="SQL test",
    )
    target_names: tuple[str, ...] = tuple(
        sorted(
            {
                _safe_segment(value=target.target_model_name, kind="test target")
                for target in test_case.target_cases
            }
        )
    )
    folder: Path = (
        Path(target_names[0])
        if len(target_names) == 1
        else Path("_chain_", "__".join(target_names))
    )
    return Path("compiled", "tests", folder, f"{test_name}.sql")


def runtime_test_path(*, test_case: SqlTestCase) -> Path:
    return Path("run", *static_test_path(test_case=test_case).parts[1:])


def _audit_relative_path(*, file_path: Path, project_dir: Path) -> Path:
    resolved_file_path: Path = file_path.resolve()
    resolved_project_dir: Path = project_dir.resolve()
    audits_root: Path = resolved_project_dir / "audits"
    try:
        return resolved_file_path.relative_to(audits_root)
    except ValueError:
        try:
            return resolved_file_path.relative_to(resolved_project_dir)
        except ValueError as error:
            raise CompileArtifactError(
                f"Audit file '{file_path}' is outside project root '{project_dir}'"
            ) from error


def _safe_segment(*, value: str, kind: str) -> str:
    candidate: Path = Path(value)
    if (
        not value
        or candidate.is_absolute()
        or value in UNSAFE_ARTIFACT_PATH_SEGMENTS
        or any(separator in value for separator in ARTIFACT_PATH_SEPARATORS)
    ):
        raise CompileArtifactError(f"Unsafe {kind} artifact path segment '{value}'")
    return value
