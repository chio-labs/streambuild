"""Expose render-only source planning within the executor domain."""

from streambuild.compiler.compile.models import DesiredState
from streambuild.executor.population._helpers.sources import plan_population_sources as _plan
from streambuild.executor.population.models import (
    PopulationRealization,
    PopulationSourcePreparation,
)


def plan_population_sources(
    *,
    desired_state: DesiredState,
    default_database: str,
    existing_relation_names: frozenset[str],
) -> tuple[PopulationSourcePreparation, tuple[PopulationRealization, ...]]:
    """Return passive source resources and deferred attachments without mutation."""

    return _plan(
        desired_state=desired_state,
        default_database=default_database,
        existing_relation_names=existing_relation_names,
    )
