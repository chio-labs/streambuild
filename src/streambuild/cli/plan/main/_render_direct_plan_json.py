"""Render one direct plan as deterministic JSON."""

from streambuild.cli.plan._helpers.direct_rendering import (
    render_direct_plan_json as _render_direct_plan_json,
)
from streambuild.compiler.planner.models import DirectPlan


def render_direct_plan_json(*, plan: DirectPlan, adapter_name: str) -> str:
    """Return the complete direct plan as deterministic JSON."""

    return _render_direct_plan_json(plan=plan, adapter_name=adapter_name)
