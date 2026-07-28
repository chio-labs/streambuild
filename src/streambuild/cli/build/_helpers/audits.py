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

    audits: tuple[LoadedSqlAudit, ...] = preview.analysis.compiled_project.audits
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
