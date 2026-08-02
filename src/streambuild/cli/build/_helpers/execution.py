"""Confirmation gate and execution of one previewed direct build."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.confirmation import confirm_build
from streambuild.cli.build.models import BuildCommandOptions, DirectWorkflowPreparation
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.executor.direct.main.build_direct_execution_result import (
    build_direct_execution_result,
)
from streambuild.executor.direct.models import (
    DirectBuildExecutionResult,
)
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main.execute_build_workflow import execute_build_workflow
from streambuild.executor.workflow.models import (
    PublishedBuildWorkflow,
    WorkflowExecutionResult,
)


def execute_confirmed_direct_build(
    *,
    preparation: DirectWorkflowPreparation,
    options: BuildCommandOptions,
    client: AdapterConnection,
) -> DirectBuildExecutionResult | None:
    """Show the destructive plan, require confirmation, then build."""

    if not confirm_build(options=options, plan_text=preparation.plan_text):
        print("Build cancelled.")
        return None
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
    return build_direct_execution_result(request=preparation.request, execution=execution)
