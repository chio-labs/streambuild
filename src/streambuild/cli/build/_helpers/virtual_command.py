"""Execute one confirmed virtual-environment build command."""

import json

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.confirmation import confirm_build
from streambuild.cli.build._helpers.virtual_preview import build_virtual_build_preview
from streambuild.cli.build.main.render_virtual_build_result import render_virtual_build_result
from streambuild.cli.build.models import BuildCommandOptions, VirtualBuildPreviewContext
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.main._normalize_cli_start_time import normalize_cli_start_time
from streambuild.cli.plan.main.render_plan_result import render_plan_result
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.backfill.main.assemble_virtual_build_workflow import (
    assemble_virtual_build_workflow,
)
from streambuild.executor.backfill.main.build_virtual_execution_result import (
    build_virtual_execution_result,
)
from streambuild.executor.backfill.models import BackfillBootstrapRequest, BackfillExecutionResult
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main.execute_build_workflow import execute_build_workflow
from streambuild.executor.workflow.models import (
    BuildWorkflow,
    PublishedBuildWorkflow,
    WorkflowExecutionResult,
)


def execute_virtual_build_command(
    *, analysis: CompileAnalysis, options: BuildCommandOptions, client: AdapterConnection
) -> int:
    """Plan, confirm, and populate one isolated virtual deployment."""

    start_time_utc: str | None = _validated_start_time(options=options)
    preview: VirtualBuildPreviewContext = build_virtual_build_preview(
        options=options,
        start_time_utc=start_time_utc,
        client=client,
        analysis=analysis,
    )
    plan_text: str = render_plan_result(
        plan=preview.plan,
        desired_state=preview.desired_state,
        database=preview.database,
        adapter_name=client.adapter_identity.name,
        json_output=False,
        verbose=options.verbose,
    )
    if not confirm_build(options=options, plan_text=plan_text):
        print("Build cancelled.")
        return 1
    serialized_plan_payload: dict[str, object] = json.loads(
        render_plan_result(
            plan=preview.plan,
            desired_state=preview.desired_state,
            database=preview.database,
            adapter_name=client.adapter_identity.name,
            json_output=True,
            verbose=options.verbose,
        )
    )
    serialized_plan_payload["deployment_created_at"] = preview.created_at
    request: BackfillBootstrapRequest = BackfillBootstrapRequest(
        desired_state=preview.desired_state,
        default_database=preview.database,
        metadata_database=preview.metadata_database,
        replay_lineage_mode=preview.replay_lineage_mode,
        confirmed_plan=preview.plan,
        deployment_id=preview.deployment_id,
        full_refresh_keys=preview.full_refresh_keys,
        start_time_keys=preview.start_time_keys,
        start_time=preview.start_time,
        created_at=preview.created_at,
        confirmed_target_catalog=preview.target_catalog,
        confirmed_metadata_catalog=preview.metadata_catalog,
    )
    workflow: BuildWorkflow = assemble_virtual_build_workflow(
        request=request,
        client=client,
        plan_json=json.dumps(serialized_plan_payload, indent=2),
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
        raise error.cause from error
    result: BackfillExecutionResult = build_virtual_execution_result(
        request=request,
        root_reports=preview.root_reports,
        existing_relation_names=preview.existing_relation_names,
        execution=execution,
    )
    print(
        render_virtual_build_result(
            result=result,
            database=preview.database,
            json_output=options.json_output,
        )
    )
    return 0


def _validated_start_time(*, options: BuildCommandOptions) -> str | None:
    if options.full_refresh and options.start_time is not None:
        raise CliUserError("--full-refresh cannot be combined with --start-time")
    if (options.full_refresh or options.start_time is not None) and not options.selectors:
        required_flag: str = "--full-refresh" if options.full_refresh else "--start-time"
        raise CliUserError(f"{required_flag} requires at least one --select")
    if options.start_time is None:
        return None
    return normalize_cli_start_time(options.start_time)
