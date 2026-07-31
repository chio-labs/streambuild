"""Internal entrypoint for passive managed-source population preparation."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.models import DesiredState
from streambuild.executor.population._helpers.sources import prepare_population_sources_impl
from streambuild.executor.population.models import PopulationSourcePreparation


def prepare_population_sources(
    *,
    client: AdapterConnection,
    desired_state: DesiredState,
    default_database: str,
    existing_relation_names: frozenset[str],
) -> PopulationSourcePreparation:
    """Create absent passive source resources and defer landing activation."""

    return prepare_population_sources_impl(
        client=client,
        desired_state=desired_state,
        default_database=default_database,
        existing_relation_names=existing_relation_names,
    )
