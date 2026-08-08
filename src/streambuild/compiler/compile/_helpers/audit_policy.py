"""Resolve effective audit policy across project, pipelines, and audit overrides."""

from dataclasses import replace

from streambuild.compiler.audit_discovery.constants import (
    DEFAULT_AUDIT_SEVERITY,
    WARNING_AUDIT_SEVERITY,
)
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.audit_discovery.types import AuditAttachmentKind
from streambuild.compiler.compile.exceptions import AuditCompileError
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.models import AuditDefaults


def resolve_audit_policies(
    *,
    audits: tuple[LoadedSqlAudit, ...],
    compiled_pipelines: tuple[CompiledPipeline, ...],
    project_defaults: AuditDefaults,
) -> tuple[LoadedSqlAudit, ...]:
    """Apply deterministic policy precedence to every validated audit."""

    defaults_by_model: dict[str, AuditDefaults] = {}
    for pipeline in compiled_pipelines:
        effective_defaults: AuditDefaults = _effective_defaults(
            project=project_defaults,
            pipeline=pipeline.pipeline.audit_defaults,
        )
        for model in pipeline.models:
            defaults_by_model[model.key.name] = effective_defaults
    return tuple(
        _resolve_audit_policy(audit=audit, defaults_by_model=defaults_by_model) for audit in audits
    )


def _effective_defaults(*, project: AuditDefaults, pipeline: AuditDefaults) -> AuditDefaults:
    return AuditDefaults(
        severity=pipeline.severity or project.severity or DEFAULT_AUDIT_SEVERITY,
        cadence_seconds=(
            pipeline.cadence_seconds
            if pipeline.cadence_seconds is not None
            else project.cadence_seconds
        ),
        warmup_seconds=(
            pipeline.warmup_seconds
            if pipeline.warmup_seconds is not None
            else (project.warmup_seconds or 0)
        ),
    )


def _resolve_audit_policy(
    *, audit: LoadedSqlAudit, defaults_by_model: dict[str, AuditDefaults]
) -> LoadedSqlAudit:
    inherited: tuple[AuditDefaults, ...] = tuple(
        defaults_by_model[model_name] for model_name in audit.referenced_model_names
    )
    severity: str = (
        audit.severity
        if audit.severity_is_explicit
        else (
            DEFAULT_AUDIT_SEVERITY
            if any(item.severity == DEFAULT_AUDIT_SEVERITY for item in inherited)
            else WARNING_AUDIT_SEVERITY
        )
    )
    warmup_seconds: int = (
        audit.warmup_seconds_override
        if audit.warmup_seconds_override is not None
        else max(int(item.warmup_seconds or 0) for item in inherited)
    )
    inherited_cadences: frozenset[int] = frozenset(
        item.cadence_seconds for item in inherited if item.cadence_seconds is not None
    )
    if audit.cadence_seconds_override is None and len(inherited_cadences) > 1:
        raise AuditCompileError(
            f"SQL audit '{audit.name or audit.file_path.stem}' inherits conflicting pipeline "
            "cadences; define every on the audit"
        )
    cadence_seconds: int | None = (
        audit.cadence_seconds_override
        if audit.cadence_seconds_override is not None
        else next(iter(inherited_cadences), None)
    )
    if audit.scheduled_override is False:
        cadence_seconds = None
    scheduled: bool = cadence_seconds is not None
    if audit.scheduled_override is True and cadence_seconds is None:
        raise AuditCompileError(
            f"SQL audit '{audit.name or audit.file_path.stem}' sets scheduled: true without "
            "an effective cadence"
        )
    if scheduled and audit.attachment_kind == AuditAttachmentKind.STANDALONE and audit.name is None:
        raise AuditCompileError(
            f"Scheduled SQL audit '{audit.file_path}' must define an explicit stable name"
        )
    return replace(
        audit,
        severity=severity,
        cadence_seconds=cadence_seconds,
        warmup_seconds=warmup_seconds,
        scheduled=scheduled,
    )
