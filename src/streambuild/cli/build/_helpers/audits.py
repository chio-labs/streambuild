"""Run user SQL audits after standard resources are live under D-025."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build.models import BuildPreviewContext
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.executor.auditing.main.execute_sql_audits import execute_sql_audits
from streambuild.executor.auditing.models import SqlAuditRunResult


def run_standard_build_audits(
    *,
    preview: BuildPreviewContext,
    client: AdapterConnection,
    adapter_profile: CompilerAdapterProfile,
) -> SqlAuditRunResult:
    """Audit the directly named relations the build just made live."""

    audits: tuple[LoadedSqlAudit, ...] = select_standard_build_audits(
        audits=preview.analysis.compiled_project.audits,
        execution_model_names=frozenset(key.name for key in preview.plan.execution_scope),
        full_build=not preview.plan.user_scope,
    )
    return execute_sql_audits(
        loaded_audits=audits,
        resolver={
            model.key.name: (
                f"{preview.database}."
                f"{preview.analysis.realized_project.relation_name_by_logical_key[model.key]}"
            )
            for model in preview.analysis.compiled_project.models
        },
        client=client,
        dialect=adapter_profile.sql_analysis_dialect,
    )


def select_standard_build_audits(
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
