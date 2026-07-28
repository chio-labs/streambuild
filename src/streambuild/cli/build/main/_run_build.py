"""CLI command for standard-mode builds."""

import sys

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.cli.build._helpers.audits import run_standard_build_audits
from streambuild.cli.build._helpers.execution import execute_confirmed_standard_build
from streambuild.cli.build._helpers.preview import build_standard_build_preview
from streambuild.cli.build._helpers.rendering import (
    render_standard_build_json,
    render_standard_build_text,
)
from streambuild.cli.build.models import BuildCommandOptions, BuildPreviewContext
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.main.render_standard_plan_text import render_standard_plan_text
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.planner.exceptions import StandardPlanError
from streambuild.executor.auditing.models import SqlAuditRunResult
from streambuild.executor.standard.exceptions import StandardBuildError
from streambuild.executor.standard.models import StandardBuildResult


def run_build(
    *,
    options: BuildCommandOptions,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Plan, confirm, and realize one standard build, then audit the live result."""

    try:
        if options.json_output and not options.auto_approve:
            print("--json requires --auto-approve for build", file=sys.stderr)
            return 1
        preview: BuildPreviewContext = build_standard_build_preview(
            options=options,
            client=client,
            loaded_project=loaded_project,
            adapter_profile=adapter_profile,
        )
        result: StandardBuildResult | None = execute_confirmed_standard_build(
            preview=preview,
            options=options,
            client=client,
            plan_text=render_standard_plan_text(
                plan=preview.plan, adapter_name=preview.adapter_name
            ),
        )
        if result is None:
            return 1
        audit_result: SqlAuditRunResult = run_standard_build_audits(
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
        StandardPlanError,
        StandardBuildError,
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
    result: StandardBuildResult,
    audit_result: SqlAuditRunResult,
) -> str:
    if options.json_output:
        return render_standard_build_json(
            result=result,
            adapter_name=preview.adapter_name,
            audit_result=audit_result,
        )
    return render_standard_build_text(
        result=result,
        adapter_name=preview.adapter_name,
        audit_result=audit_result,
    )
