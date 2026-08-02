"""CLI command for staged backfill audit."""

import sys
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterWarehouseError
from streambuild.cli.audit_backfill._helpers.audit_execution import (
    execute_audit_quality_checks,
    resolve_deployment_candidate_error,
)
from streambuild.cli.audit_backfill.main.render_audit_backfill_result import (
    render_audit_backfill_result,
)
from streambuild.cli.entry.main._errors import render_expected_warehouse_error
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import CompiledPipeline, CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.audit_backfill.main.execute_audit_backfill import execute_audit_backfill
from streambuild.executor.audit_backfill.models import (
    AuditBackfillRequest,
    AuditBackfillResult,
)


def run_audit_backfill(
    *,
    pipelines_root: Path | None,
    project_dir: Path | None,
    database: str,
    metadata_database: str | None,
    deployment_id: str | None,
    json_output: bool,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Audit a staged backfill deployment and print the result payload."""

    resolved_metadata_database: str = metadata_database or database
    try:
        analysis: CompileAnalysis | None = (
            analyze_project(
                pipelines_root=pipelines_root,
                loaded_project=loaded_project,
                adapter_profile=adapter_profile,
            )
            if pipelines_root is not None
            else None
        )
        compiled_pipelines: tuple[CompiledPipeline, ...] = (
            () if analysis is None else analysis.compiled_project.pipelines
        )
        loaded_audits: tuple[LoadedSqlAudit, ...] = (
            () if analysis is None else analysis.compiled_project.audits
        )
        candidate_error: str | None = resolve_deployment_candidate_error(
            deployment_id=deployment_id,
            client=client,
            metadata_database=resolved_metadata_database,
            database=database,
        )
        if candidate_error is not None:
            print(candidate_error, file=sys.stderr)
            return 1
        result: AuditBackfillResult = execute_audit_backfill(
            request=AuditBackfillRequest(
                deployment_id=deployment_id,
                metadata_database=resolved_metadata_database,
                default_database=database,
            ),
            client=client,
        )
        result = execute_audit_quality_checks(
            result=result,
            project_dir=project_dir,
            compiled_pipelines=compiled_pipelines,
            loaded_audits=loaded_audits,
            client=client,
            metadata_database=resolved_metadata_database,
            database=database,
            dialect=adapter_profile.sql_analysis_dialect,
        )
    except AdapterWarehouseError as error:
        rendered_error: str | None = render_expected_warehouse_error(
            command_name="audit deployment",
            database=database,
            error=error,
        )
        if rendered_error is not None:
            print(rendered_error, file=sys.stderr)
            return 1
        raise
    print(
        render_audit_backfill_result(
            result=result,
            database=database,
            json_output=json_output,
            project_dir=project_dir,
        )
    )
    return 0
