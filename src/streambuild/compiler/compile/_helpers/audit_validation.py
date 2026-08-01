"""Validate discovered SQL audits against compiled logical models."""

from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.exceptions import AuditCompileError
from streambuild.compiler.compile.main.compiled_models import compiled_models
from streambuild.compiler.compile.models import CompiledPipeline


def validated_sql_audits(
    *,
    loaded_audits: tuple[LoadedSqlAudit, ...],
    compiled_pipelines: tuple[CompiledPipeline, ...],
) -> tuple[LoadedSqlAudit, ...]:
    """Return audits after validating each target against a compiled model."""

    known_model_names: frozenset[str] = frozenset(
        model.key.name for model in compiled_models(compiled_pipelines=compiled_pipelines)
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
