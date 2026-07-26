"""Plan rendering shared by plan and backfill preview flows."""

from __future__ import annotations

from streambuild.cli.plan._helpers.result_rendering import (
    render_plan_json,
    render_plan_text,
)
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import DeploymentPlan


def render_plan_result(
    *,
    plan: DeploymentPlan,
    desired_state: DesiredState,
    database: str,
    json_output: bool,
    verbose: bool = False,
) -> str:
    if json_output:
        return render_plan_json(plan)
    return render_plan_text(
        plan=plan,
        desired_state=desired_state,
        database=database,
        verbose=verbose,
    )
