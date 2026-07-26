"""Entry point for compiler-side SQL audit validation."""

from __future__ import annotations

from streambuild.compiler.auditing.exceptions import AuditCompileError
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.shared.main.compiled_transforms import compiled_transforms
from streambuild.compiler.shared.models import LoadedSqlAudit


def validated_sql_audits(
    *,
    loaded_audits: tuple[LoadedSqlAudit, ...],
    compiled_pipelines: tuple[CompiledPipeline, ...],
) -> tuple[LoadedSqlAudit, ...]:
    """Validate discovered SQL audits against compiled model names."""

    known_model_names: frozenset[str] = frozenset(
        compiled_transform.transform.name
        for compiled_transform in compiled_transforms(compiled_pipelines=compiled_pipelines)
    )
    loaded_audit: LoadedSqlAudit
    for loaded_audit in loaded_audits:
        unknown_model_names: tuple[str, ...] = tuple(
            model_name
            for model_name in loaded_audit.referenced_model_names
            if model_name not in known_model_names
        )
        if unknown_model_names:
            raise AuditCompileError(
                f"SQL audit '{loaded_audit.file_path}' references unknown models: "
                f"{', '.join(unknown_model_names)}"
            )
    return loaded_audits
