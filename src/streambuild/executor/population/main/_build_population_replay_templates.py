"""Expose boundary-independent replay planning within the executor domain."""

from streambuild.adapter.models import AdapterReplayRequest
from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.executor.population._helpers.replay import (
    build_population_replay_templates as _build,
)
from streambuild.executor.population.models import PopulationPlan


def build_population_replay_templates(
    *, plan: PopulationPlan, desired_state: DesiredState, default_database: str
) -> tuple[tuple[ObjectKey, AdapterReplayRequest], ...]:
    """Build one full-replay template per root without warehouse-derived values."""

    return _build(plan=plan, desired_state=desired_state, default_database=default_database)
