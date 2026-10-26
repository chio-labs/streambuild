"""Direct plan text rendering shared by plan and build flows."""

from __future__ import annotations

from streambuild.cli.plan._helpers.direct_rendering import (
    render_direct_plan_text as render_direct_plan_text_impl,
)
from streambuild.compiler.planner.models import DirectPlan
from streambuild.executor.population.models import PopulationSourceRecreation


def render_direct_plan_text(
    *,
    plan: DirectPlan,
    adapter_name: str,
    verbose: bool = False,
    source_recreations: tuple[PopulationSourceRecreation, ...] = (),
) -> str:
    """Render one direct plan as operator-facing text."""

    return render_direct_plan_text_impl(
        plan=plan,
        adapter_name=adapter_name,
        verbose=verbose,
        source_recreations=source_recreations,
    )
