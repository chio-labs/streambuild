"""Execute one confirmed virtual-environment build command."""

import sys

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterInvocationRecord
from streambuild.cli.build._helpers.confirmation import confirm_build
from streambuild.cli.build.main.render_virtual_build_result import render_virtual_build_result
from streambuild.cli.build.models import BuildCommandOptions, VirtualWorkflowPreparation
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.executor.backfill.main.build_virtual_execution_result import (
    build_virtual_execution_result,
)
from streambuild.executor.backfill.models import BackfillExecutionResult
from streambuild.executor.observability.main.build_invocation_record import (
    build_invocation_record,
)
from streambuild.executor.observability.main.persist_terminal_observations import (
    persist_terminal_observations,
)
from streambuild.executor.observability.models import TerminalInvocation
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main.execute_build_workflow import execute_build_workflow
from streambuild.executor.workflow.models import PublishedBuildWorkflow, WorkflowExecutionResult


def execute_virtual_build_command(
    *,
    preparation: VirtualWorkflowPreparation,
    options: BuildCommandOptions,
    client: AdapterConnection,
    started: tuple[str, str, int],
) -> int:
    """Confirm and populate one prepared isolated virtual deployment."""

    if not confirm_build(options=options, plan_text=preparation.plan_text):
        print("Build cancelled.")
        _persist_virtual_invocation(
            started=started,
            preparation=preparation,
            options=options,
            client=client,
            outcome="cancelled",
            exit_code=1,
            materialized_outcome=None,
            error_message=None,
        )
        return 1
    published_workflow: PublishedBuildWorkflow = publish_build_workflow(
        target_dir=options.pipelines_root.parent / "target",
        workflow=preparation.workflow,
    )
    try:
        execution: WorkflowExecutionResult = execute_build_workflow(
            published_workflow=published_workflow,
            connection=client,
        )
    except WorkflowExecutionError as error:
        print(str(error.cause), file=sys.stderr)
        _persist_virtual_invocation(
            started=started,
            preparation=preparation,
            options=options,
            client=client,
            outcome="failed",
            exit_code=1,
            materialized_outcome=None,
            error_message=str(error.cause),
        )
        return 1
    result: BackfillExecutionResult = build_virtual_execution_result(
        request=preparation.request,
        root_reports=preparation.preview.root_reports,
        existing_relation_names=preparation.preview.existing_relation_names,
        execution=execution,
    )
    print(
        render_virtual_build_result(
            result=result,
            database=preparation.preview.database,
            json_output=options.json_output,
        )
    )
    _persist_virtual_invocation(
        started=started,
        preparation=preparation,
        options=options,
        client=client,
        outcome="succeeded",
        exit_code=0,
        materialized_outcome="applied",
        error_message=None,
    )
    return 0


def _persist_virtual_invocation(
    *,
    started: tuple[str, str, int],
    preparation: VirtualWorkflowPreparation,
    options: BuildCommandOptions,
    client: AdapterConnection,
    outcome: str,
    exit_code: int,
    materialized_outcome: str | None,
    error_message: str | None,
) -> None:
    invocation: AdapterInvocationRecord = build_invocation_record(
        started=started,
        terminal=TerminalInvocation(
            project_dir=options.pipelines_root.parent,
            target_identity=preparation.preview.database,
            command="build",
            mode="virtual_environment",
            outcome=outcome,
            exit_code=exit_code,
            materialized_outcome=materialized_outcome,
            deployment_id=preparation.preview.deployment_id,
            workflow_id=None,
            selected_node_count=len(preparation.preview.plan.object_changes),
            error_message=error_message,
            summary={},
        ),
    )
    persist_terminal_observations(
        client=client,
        database=preparation.preview.metadata_database,
        invocation=invocation,
        node_results=(),
    )
