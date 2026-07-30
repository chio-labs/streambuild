"""CLI command for direct-mode builds."""

import sys

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.cli.build._helpers.audits import run_direct_build_audits
from streambuild.cli.build._helpers.execution import execute_confirmed_direct_build
from streambuild.cli.build._helpers.preview import build_direct_build_preview
from streambuild.cli.build._helpers.rendering import (
    render_direct_build_json,
    render_direct_build_text,
)
from streambuild.cli.build.models import BuildCommandOptions, BuildPreviewContext
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.main.render_direct_plan_text import render_direct_plan_text
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.executor.auditing.models import SqlAuditRunResult
from streambuild.executor.direct.exceptions import DirectBuildError
from streambuild.executor.direct.models import DirectBuildResult


def run_build(
    *,
    options: BuildCommandOptions,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Plan, confirm, and realize one direct build, then audit the live result."""

    try:
        if options.json_output and not options.auto_approve:
            print("--json requires --auto-approve for build", file=sys.stderr)
            return 1
        preview: BuildPreviewContext = build_direct_build_preview(
            options=options,
            client=client,
            loaded_project=loaded_project,
            adapter_profile=adapter_profile,
        )
        result: DirectBuildResult | None = execute_confirmed_direct_build(
            preview=preview,
            options=options,
            client=client,
            plan_text=render_direct_plan_text(plan=preview.plan, adapter_name=preview.adapter_name),
        )
        if result is None:
            return 1
        audit_result: SqlAuditRunResult = run_direct_build_audits(
            preview=preview,
            client=client,
            adapter_profile=adapter_profile,
        )
        print(
            _rendered_result(
                options=options,
                preview=preview,
                result=result,
                audit_result=audit_result,
            )
        )
    except (
        TransformSqlContractError,
        CliUserError,
        DirectPlanError,
        DirectBuildError,
        AdapterError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 1 if audit_result.error_failure_count else 0


def _rendered_result(
    *,
    options: BuildCommandOptions,
    preview: BuildPreviewContext,
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
