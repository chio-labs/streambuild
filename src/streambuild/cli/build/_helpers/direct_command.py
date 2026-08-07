"""Execute one confirmed direct-mode build command."""

import sys
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterInvocationRecord, AdapterNodeResultRecord
from streambuild.cli.build._helpers.audits import select_direct_build_audits
from streambuild.cli.build._helpers.execution import execute_confirmed_direct_build
from streambuild.cli.build._helpers.rendering import (
    render_direct_build_json,
    render_direct_build_text,
)
from streambuild.cli.build.models import (
    BuildCommandOptions,
    DirectBuildPreviewContext,
    DirectWorkflowPreparation,
)
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.executor.auditing.models import SqlAuditResult, SqlAuditRunResult
from streambuild.executor.auditing.types import AuditSeverity
from streambuild.executor.direct.models import (
    DirectBuildExecutionResult,
    DirectBuildResult,
)
from streambuild.executor.observability.classes.run_event_sink import RunEventSink
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
from streambuild.executor.observability.models import TerminalInvocation

_SIGINT_EXIT_CODE: int = 130


def execute_direct_build_command(
    *,
    preparation: DirectWorkflowPreparation,
    options: BuildCommandOptions,
    client: AdapterConnection,
    observation_client: AdapterConnection,
    started: tuple[str, str, int],
) -> int:
    """Confirm, execute, and audit one prepared direct build."""

    sink: RunEventSink = _build_event_sink(
        options=options,
        client=observation_client,
        preparation=preparation,
        invocation_id=started[0],
    )
    try:
        if sink is not None:
            sink.run_started(
                command="build",
                mode="direct",
                total_statements=len(preparation.workflow.statements),
                selected_node_count=len(preparation.preview.plan.execution_scope),
            )
        execution: DirectBuildExecutionResult | None = execute_confirmed_direct_build(
            preparation=preparation,
            options=options,
            client=client,
            emitter=sink,
        )
    except (AdapterError, OSError) as error:
        failed_invocation: AdapterInvocationRecord = _build_invocation(
            started=started,
            preparation=preparation,
            options=options,
            exit_code=1,
            outcome="failed",
            materialized_outcome=None,
            audit_result=None,
            error_message=str(error),
        )
        _persist_terminal_observations(
            client=client,
            database=preparation.preview.metadata_database,
            invocation=failed_invocation,
            node_results=(),
        )
        if sink is not None:
            sink.run_completed(outcome="failed", exit_code=1, error_message=str(error))
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        interrupted_invocation: AdapterInvocationRecord = _build_invocation(
            started=started,
            preparation=preparation,
            options=options,
            exit_code=_SIGINT_EXIT_CODE,
            outcome="cancelled",
            materialized_outcome=None,
            audit_result=None,
            error_message=None,
        )
        _persist_terminal_observations(
            client=client,
            database=preparation.preview.metadata_database,
            invocation=interrupted_invocation,
            node_results=(),
        )
        if sink is not None:
            sink.run_completed(outcome="cancelled", exit_code=_SIGINT_EXIT_CODE, error_message=None)
        try:
            print("build interrupted; recorded as cancelled", file=sys.stderr)
        except Exception:
            pass
        return _SIGINT_EXIT_CODE
    if execution is None:
        invocation: AdapterInvocationRecord = _build_invocation(
            started=started,
            preparation=preparation,
            options=options,
            exit_code=1,
            outcome="cancelled",
            materialized_outcome=None,
            audit_result=None,
            error_message=None,
        )
        _persist_terminal_observations(
            client=client,
            database=preparation.preview.metadata_database,
            invocation=invocation,
            node_results=(),
        )
        if sink is not None:
            sink.run_completed(outcome="cancelled", exit_code=1, error_message=None)
        print("Build cancelled.")
        return 1
    exit_code: int = 1 if execution.audit_result.error_failure_count else 0
    invocation = _build_invocation(
        started=started,
        preparation=preparation,
        options=options,
        exit_code=exit_code,
        outcome="failed" if exit_code else "succeeded",
        materialized_outcome="applied",
        audit_result=execution.audit_result,
        error_message=None,
    )
    selected_audits: tuple[LoadedSqlAudit, ...] = select_direct_build_audits(
        audits=preparation.preview.analysis.compiled_project.audits,
        execution_model_names=frozenset(
            key.name for key in preparation.preview.plan.execution_scope
        ),
        full_build=not preparation.preview.plan.user_scope,
    )
    node_results: tuple[AdapterNodeResultRecord, ...] = _direct_audit_node_results(
        invocation=invocation,
        audits=selected_audits,
        audit_result=execution.audit_result,
        project_dir=options.pipelines_root.parent,
    )
    _persist_terminal_observations(
        client=client,
        database=preparation.preview.metadata_database,
        invocation=invocation,
        node_results=node_results,
    )
    if sink is not None:
        sink.run_completed(
            outcome="failed" if exit_code else "succeeded",
            exit_code=exit_code,
            error_message=None,
        )
    if not options.events_output:
        print(
            _rendered_result(
                options=options,
                preview=preparation.preview,
                result=execution.build_result,
                audit_result=execution.audit_result,
            )
        )
    return exit_code


def _persist_terminal_observations(
    *,
    client: AdapterConnection,
    database: str,
    invocation: AdapterInvocationRecord,
    node_results: tuple[AdapterNodeResultRecord, ...],
) -> None:
    warning: str | None = persist_terminal_observations(
        client=client,
        database=database,
        invocation=invocation,
        node_results=node_results,
    )
    if warning is not None:
        try:
            print(warning, file=sys.stderr)
        except Exception:
            return


def _build_event_sink(
    *,
    options: BuildCommandOptions,
    client: AdapterConnection,
    preparation: DirectWorkflowPreparation,
    invocation_id: str,
) -> RunEventSink:
    return RunEventSink(
        connection=client,
        database=preparation.preview.metadata_database,
        invocation_id=invocation_id,
        jsonl_stream=sys.stdout if options.events_output else None,
    )


def _direct_audit_node_results(
    *,
    invocation: AdapterInvocationRecord,
    audits: tuple[LoadedSqlAudit, ...],
    audit_result: SqlAuditRunResult,
    project_dir: Path,
) -> tuple[AdapterNodeResultRecord, ...]:
    records: list[AdapterNodeResultRecord] = []
    audit: LoadedSqlAudit
    result: SqlAuditResult
    for audit, result in zip(audits, audit_result.audit_results, strict=True):
        status: str = (
            "error"
            if result.error_message is not None
            else (
                "passed"
                if result.passed
                else ("warning" if result.severity == AuditSeverity.WARNING else "failed")
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
                severity=result.severity,
                failure_count=result.failing_row_count,
                payload={
                    "sample_column_names": list(result.sample_column_names),
                    "sample_rows": [list(row) for row in result.sample_rows[:5]],
                },
                error_message=result.error_message,
            )
        )
    return tuple(records)


def _build_invocation(
    *,
    started: tuple[str, str, int],
    preparation: DirectWorkflowPreparation,
    options: BuildCommandOptions,
    exit_code: int,
    outcome: str,
    materialized_outcome: str | None,
    audit_result: SqlAuditRunResult | None,
    error_message: str | None,
) -> AdapterInvocationRecord:
    return build_invocation_record(
        started=started,
        terminal=TerminalInvocation(
            project_dir=options.pipelines_root.parent,
            target_identity=preparation.preview.database,
            command="build",
            mode="direct",
            outcome=outcome,
            exit_code=exit_code,
            materialized_outcome=materialized_outcome,
            deployment_id=None,
            workflow_id=None,
            selected_node_count=len(preparation.preview.plan.execution_scope),
            error_message=error_message,
            summary={
                "audit_error_failure_count": (
                    audit_result.error_failure_count if audit_result is not None else 0
                ),
                "audit_warning_failure_count": (
                    audit_result.warning_failure_count if audit_result is not None else 0
                ),
            },
        ),
    )


def _rendered_result(
    *,
    options: BuildCommandOptions,
    preview: DirectBuildPreviewContext,
    result: DirectBuildResult,
    audit_result: SqlAuditRunResult,
) -> str:
    if options.json_output:
        return render_direct_build_json(
            result=result,
            adapter_name=preview.adapter_name,
            audit_result=audit_result,
        )
    return render_direct_build_text(
        result=result,
        adapter_name=preview.adapter_name,
        audit_result=audit_result,
    )
