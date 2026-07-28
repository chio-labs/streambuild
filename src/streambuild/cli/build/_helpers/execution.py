"""Confirmation gate and execution of one previewed standard build."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build.models import BuildCommandOptions, BuildPreviewContext
from streambuild.cli.entry.constants import AFFIRMATIVE_RESPONSES
from streambuild.executor.standard.main.execute_standard_build import execute_standard_build
from streambuild.executor.standard.models import StandardBuildRequest, StandardBuildResult
from streambuild.cli.build.constants import STREAMBUILD_TOOL_VERSION


def execute_confirmed_standard_build(
    *,
    preview: BuildPreviewContext,
    options: BuildCommandOptions,
    client: AdapterConnection,
    plan_text: str,
) -> StandardBuildResult | None:
    """Show the destructive plan, honor D-018 confirmation, then build."""

    _announce_plan(options=options, plan_text=plan_text)
    if not _approved(options=options):
        print("Build cancelled.")
        return None
    return execute_standard_build(
        request=StandardBuildRequest(
            plan=preview.plan,
            realized_project=preview.analysis.realized_project,
            database=preview.database,
            metadata_database=preview.metadata_database,
            tool_version=STREAMBUILD_TOOL_VERSION,
        ),
        client=client,
    )


def _announce_plan(*, options: BuildCommandOptions, plan_text: str) -> None:
    if options.json_output:
        return
    print(plan_text)


def _approved(*, options: BuildCommandOptions) -> bool:
    if options.auto_approve:
        return True
    return input("Proceed with build? [y/N] ").strip().lower() in AFFIRMATIVE_RESPONSES
