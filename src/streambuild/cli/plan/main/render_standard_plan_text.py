"""Standard plan text rendering shared by plan and build flows."""

from __future__ import annotations

from streambuild.cli.plan._helpers.standard_rendering import (
    render_standard_plan_text as render_standard_plan_text_impl,
)
from streambuild.compiler.planner.models import StandardPlan


def render_standard_plan_text(*, plan: StandardPlan, adapter_name: str) -> str:
    """Render one standard plan as operator-facing text."""

    return render_standard_plan_text_impl(plan=plan, adapter_name=adapter_name)
