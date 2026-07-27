"""CLI command for live SQL audits."""

from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.audit._helpers.rendering import render_sql_audit_run_result
from streambuild.cli.audit._helpers.selection import select_loaded_sql_audits
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import CompiledPipeline, CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.auditing.main.execute_sql_audits import execute_sql_audits
from streambuild.executor.auditing.models import SqlAuditRunResult


def run_audit(
    *,
    pipelines_root: Path,
    project_dir: Path,
    database: str,
    selectors: tuple[str, ...],
    json_output: bool,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Run user-defined SQL audits against published logical views."""

    analysis: CompileAnalysis = analyze_project(
        pipelines_root=pipelines_root,
        loaded_project=loaded_project,
        adapter_profile=adapter_profile,
    )
    compiled_pipelines: tuple[CompiledPipeline, ...] = analysis.compiled_project.pipelines
    loaded_audits: tuple[LoadedSqlAudit, ...] = analysis.compiled_project.audits
    selected_audits: tuple[LoadedSqlAudit, ...] = select_loaded_sql_audits(
        loaded_audits=loaded_audits,
        compiled_pipelines=compiled_pipelines,
        selectors=selectors,
    )
    result: SqlAuditRunResult = execute_sql_audits(
        loaded_audits=selected_audits,
        resolver={
            model.key.name: (
                f"{database}.{analysis.realized_project.relation_name_by_logical_key[model.key]}"
            )
            for model in analysis.compiled_project.models
        },
        client=client,
        dialect=adapter_profile.sql_analysis_dialect,
    )
    print(
        render_sql_audit_run_result(
            result=result,
            database=database,
            project_dir=project_dir,
            json_output=json_output,
        )
    )
    return 1 if result.error_failure_count else 0
