"""Confirmation gate and execution of one previewed direct build."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.confirmation import confirm_build
from streambuild.cli.build.constants import STREAMBUILD_TOOL_VERSION
from streambuild.cli.build.models import BuildCommandOptions, DirectBuildPreviewContext
from streambuild.cli.plan.main._render_direct_plan_json import render_direct_plan_json
from streambuild.cli.workflow_artifacts.main._write_plan_artifact import write_plan_artifact
from streambuild.cli.workflow_artifacts.types import WorkflowArtifactOwner
from streambuild.executor.direct.main.execute_direct_build import execute_direct_build
from streambuild.executor.direct.models import DirectBuildRequest, DirectBuildResult


def execute_confirmed_direct_build(
    *,
    preview: DirectBuildPreviewContext,
    options: BuildCommandOptions,
    client: AdapterConnection,
    plan_text: str,
) -> DirectBuildResult | None:
    """Show the destructive plan, require confirmation, then build."""

    if not confirm_build(options=options, plan_text=plan_text):
        print("Build cancelled.")
        return None
    write_plan_artifact(
        target_dir=options.pipelines_root.parent / "target",
        owner=WorkflowArtifactOwner.BUILD,
        contents=render_direct_plan_json(plan=preview.plan, adapter_name=preview.adapter_name),
    )
    return execute_direct_build(
        request=DirectBuildRequest(
            plan=preview.plan,
            realized_project=preview.analysis.realized_project,
            database=preview.database,
            metadata_database=preview.metadata_database,
            tool_version=STREAMBUILD_TOOL_VERSION,
        ),
        client=client,
    )
