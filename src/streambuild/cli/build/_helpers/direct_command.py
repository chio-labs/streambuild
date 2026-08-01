"""Execute one confirmed direct-mode build command."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.audits import run_direct_build_audits
from streambuild.cli.build._helpers.execution import execute_confirmed_direct_build
from streambuild.cli.build._helpers.preview import build_direct_build_preview
from streambuild.cli.build._helpers.rendering import (
    render_direct_build_json,
    render_direct_build_text,
)
from streambuild.cli.build.models import BuildCommandOptions, DirectBuildPreviewContext
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.main.render_direct_plan_text import render_direct_plan_text
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.auditing.models import SqlAuditRunResult
from streambuild.executor.direct.models import DirectBuildResult


def execute_direct_build_command(
    *,
    analysis: CompileAnalysis,
    options: BuildCommandOptions,
    client: AdapterConnection,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Plan, confirm, execute, and audit one direct build."""

    _reject_virtual_build_options(options=options)
    preview: DirectBuildPreviewContext = build_direct_build_preview(
        options=options,
        client=client,
        analysis=analysis,
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
        _rendered_result(options=options, preview=preview, result=result, audit_result=audit_result)
    )
    return 1 if audit_result.error_failure_count else 0


def _reject_virtual_build_options(*, options: BuildCommandOptions) -> None:
    if options.deployment_id is not None:
        raise CliUserError("--deployment-id requires virtual environments")
    if options.full_refresh:
        raise CliUserError("--full-refresh requires virtual environments")
    if options.start_time is not None:
        raise CliUserError("--start-time requires virtual environments")


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
