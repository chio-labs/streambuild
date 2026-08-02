"""Expose render-only realization planning within the executor domain."""

from streambuild.compiler.compile.models import DesiredState
from streambuild.executor.population._helpers.relations import plan_population_objects as _plan
from streambuild.executor.population.models import PopulationPlan, PopulationRealization


def plan_population_objects(
    *, plan: PopulationPlan, desired_state: DesiredState, default_database: str
) -> tuple[PopulationRealization, ...]:
    """Return population resources in the shared realization order."""

    return _plan(plan=plan, desired_state=desired_state, default_database=default_database)
