"""Execute one confirmed virtual-environment build command."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.confirmation import confirm_build
from streambuild.cli.build.main.render_virtual_build_result import render_virtual_build_result
from streambuild.cli.build.models import BuildCommandOptions, VirtualWorkflowPreparation
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.executor.backfill.main.build_virtual_execution_result import (
    build_virtual_execution_result,
)
from streambuild.executor.backfill.models import BackfillExecutionResult
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main.execute_build_workflow import execute_build_workflow
from streambuild.executor.workflow.models import PublishedBuildWorkflow, WorkflowExecutionResult


def execute_virtual_build_command(
    *,
    preparation: VirtualWorkflowPreparation,
    options: BuildCommandOptions,
    client: AdapterConnection,
) -> int:
    """Confirm and populate one prepared isolated virtual deployment."""

    if not confirm_build(options=options, plan_text=preparation.plan_text):
        print("Build cancelled.")
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
        raise error.cause from error
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
    return 0
