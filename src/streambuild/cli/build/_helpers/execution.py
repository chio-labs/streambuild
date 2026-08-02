"""Confirmation gate and execution of one previewed direct build."""

from __future__ import annotations

from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.confirmation import confirm_build
from streambuild.cli.build.constants import STREAMBUILD_TOOL_VERSION
from streambuild.cli.build.models import BuildCommandOptions, DirectBuildPreviewContext
from streambuild.cli.plan.main._render_direct_plan_json import render_direct_plan_json
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.executor.direct.main.assemble_direct_build_workflow import (
    assemble_direct_build_workflow,
)
from streambuild.executor.direct.main.build_direct_execution_result import (
    build_direct_execution_result,
)
from streambuild.executor.direct.models import (
    DirectBuildAudit,
    DirectBuildExecutionResult,
    DirectBuildRequest,
)
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main.execute_build_workflow import execute_build_workflow
from streambuild.executor.workflow.models import (
    BuildWorkflow,
    PublishedBuildWorkflow,
    WorkflowExecutionResult,
)


def execute_confirmed_direct_build(
    *,
    preview: DirectBuildPreviewContext,
    options: BuildCommandOptions,
    client: AdapterConnection,
    plan_text: str,
    audits: tuple[DirectBuildAudit, ...],
) -> DirectBuildExecutionResult | None:
    """Show the destructive plan, require confirmation, then build."""

    if not confirm_build(options=options, plan_text=plan_text):
        print("Build cancelled.")
        return None
    request: DirectBuildRequest = DirectBuildRequest(
        plan=preview.plan,
        realized_project=preview.analysis.realized_project,
        database=preview.database,
        metadata_database=preview.metadata_database,
        tool_version=STREAMBUILD_TOOL_VERSION,
        audits=audits,
    )
    workflow: BuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=client,
        plan_json=render_direct_plan_json(plan=preview.plan, adapter_name=preview.adapter_name),
    )
    published_workflow: PublishedBuildWorkflow = publish_build_workflow(
        target_dir=options.pipelines_root.parent / "target",
        workflow=workflow,
    )
    try:
        execution: WorkflowExecutionResult = execute_build_workflow(
            published_workflow=published_workflow,
            connection=client,
        )
    except WorkflowExecutionError as error:
        if not error.failed_step_id.startswith("audit_"):
            raise error.cause from error
        return build_direct_execution_result(
            request=request,
            execution=cast(WorkflowExecutionResult, error.partial_result),
            failed_audit_step_id=error.failed_step_id,
        )
    return build_direct_execution_result(request=request, execution=execution)
