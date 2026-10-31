"""Expose fan-in population expansion within the executor domain."""

from sqltide.compiler.compile.models import DesiredState
from sqltide.executor.population._helpers.roots import expand_fan_in_roots
from sqltide.executor.population.models import PopulationPlan


def expand_population_plan(*, plan: PopulationPlan, desired_state: DesiredState) -> PopulationPlan:
    """Expand one plan with the shared fan-in catch-up roots."""

    return expand_fan_in_roots(plan=plan, desired_state=desired_state)
