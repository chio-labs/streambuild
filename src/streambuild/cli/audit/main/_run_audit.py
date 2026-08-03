"""CLI command for live SQL audits."""

from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterInvocationRecord, AdapterNodeResultRecord
from streambuild.cli.audit._helpers.rendering import render_sql_audit_run_result
from streambuild.cli.audit._helpers.selection import select_loaded_sql_audits
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import CompiledPipeline, CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.auditing.main.execute_sql_audits import execute_sql_audits
from streambuild.executor.auditing.models import SqlAuditResult, SqlAuditRunResult
from streambuild.executor.auditing.types import AuditSeverity
from streambuild.executor.observability.main.build_invocation_record import (
    build_invocation_record,
)
from streambuild.executor.observability.main.build_node_result_record import (
    build_node_result_record,
)
from streambuild.executor.observability.main.build_quality_node_identity import (
    build_quality_node_identity,
)
from streambuild.executor.observability.main.persist_terminal_observations import (
    persist_terminal_observations,
)
from streambuild.executor.observability.main.start_invocation import start_invocation
from streambuild.executor.observability.models import TerminalInvocation


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

    started: tuple[str, str, int] = start_invocation()
    selected_node_count = 0
    try:
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
        selected_node_count = len(selected_audits)
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
    except Exception as error:
        failed_invocation: AdapterInvocationRecord = build_invocation_record(
            started=started,
            terminal=TerminalInvocation(
                project_dir=project_dir,
                target_identity=database,
                command="audit",
                mode=None,
                outcome="failed",
                exit_code=1,
                materialized_outcome=None,
                deployment_id=None,
                workflow_id=None,
                selected_node_count=selected_node_count,
                error_message=str(error),
                summary={"failed_before_results": True},
            ),
        )
        persist_terminal_observations(
            client=client,
            database=database,
            invocation=failed_invocation,
            node_results=(),
        )
        raise
    exit_code: int = 1 if result.error_failure_count else 0
    invocation: AdapterInvocationRecord = build_invocation_record(
        started=started,
        terminal=TerminalInvocation(
            project_dir=project_dir,
            target_identity=database,
            command="audit",
            mode=None,
            outcome="failed" if exit_code else "succeeded",
            exit_code=exit_code,
            materialized_outcome=None,
            deployment_id=None,
            workflow_id=None,
            selected_node_count=len(selected_audits),
            error_message=None,
            summary={
                "error_failure_count": result.error_failure_count,
                "warning_failure_count": result.warning_failure_count,
            },
        ),
    )
    node_results: tuple[AdapterNodeResultRecord, ...] = _audit_node_results(
        invocation=invocation,
        audits=selected_audits,
        result=result,
        project_dir=project_dir,
    )
    persist_terminal_observations(
        client=client,
        database=database,
        invocation=invocation,
        node_results=node_results,
    )
    return exit_code


def _audit_node_results(
    *,
    invocation: AdapterInvocationRecord,
    audits: tuple[LoadedSqlAudit, ...],
    result: SqlAuditRunResult,
    project_dir: Path,
) -> tuple[AdapterNodeResultRecord, ...]:
    records: list[AdapterNodeResultRecord] = []
    audit: LoadedSqlAudit
    audit_result: SqlAuditResult
    for audit, audit_result in zip(audits, result.audit_results, strict=True):
        status: str = (
            "error"
            if audit_result.error_message is not None
            else (
                "passed"
                if audit_result.passed
                else ("warning" if audit_result.severity == AuditSeverity.WARNING else "failed")
            )
        )
        records.append(
            build_node_result_record(
                invocation=invocation,
                node_kind="audit",
                node_identity=build_quality_node_identity(
                    project_dir=project_dir,
                    file_path=audit.file_path,
                    node_index=audit.audit_index,
                ),
                definition=audit.query,
                status=status,
                severity=audit_result.severity,
                failure_count=audit_result.failing_row_count,
                payload={
                    "sample_column_names": list(audit_result.sample_column_names),
                    "sample_rows": [list(row) for row in audit_result.sample_rows[:5]],
                },
                error_message=audit_result.error_message,
            )
        )
    return tuple(records)
