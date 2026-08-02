"""Run user SQL audits after direct resources are live."""

from __future__ import annotations

from streambuild.cli.build.models import DirectBuildPreviewContext
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.main.replace_refs import replace_refs
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import SqlReferenceRewriter
from streambuild.executor.direct.models import DirectBuildAudit


def prepare_direct_build_audits(
    *,
    preview: DirectBuildPreviewContext,
    adapter_profile: CompilerAdapterProfile,
) -> tuple[DirectBuildAudit, ...]:
    """Resolve selected direct audits before authoritative workflow construction."""

    audits: tuple[LoadedSqlAudit, ...] = select_direct_build_audits(
        audits=preview.analysis.compiled_project.audits,
        execution_model_names=frozenset(key.name for key in preview.plan.execution_scope),
        full_build=not preview.plan.user_scope,
    )
    resolver: dict[str, str] = {
        model.key.name: (
            f"{preview.database}."
            f"{preview.analysis.realized_project.relation_name_by_logical_key[model.key]}"
        )
        for model in preview.analysis.compiled_project.models
    }
    rewriter: SqlReferenceRewriter = SqlReferenceRewriter(
        dialect=adapter_profile.sql_analysis_dialect
    )
    return tuple(
        DirectBuildAudit(
            name=audit.name or audit.file_path.name,
            query=replace_refs(sql=audit.query, resolver=resolver, rewriter=rewriter),
            severity=audit.severity,
            description=audit.description,
        )
        for audit in audits
    )


def select_direct_build_audits(
    *,
    audits: tuple[LoadedSqlAudit, ...],
    execution_model_names: frozenset[str],
    full_build: bool,
) -> tuple[LoadedSqlAudit, ...]:
    """Keep audits whose complete managed-model reference set was rebuilt."""

    if full_build:
        return audits
    return tuple(
        audit
        for audit in audits
        if _is_audit_fully_covered(audit=audit, execution_model_names=execution_model_names)
    )


def _is_audit_fully_covered(
    *, audit: LoadedSqlAudit, execution_model_names: frozenset[str]
) -> bool:
    return frozenset(audit.referenced_model_names) <= execution_model_names
