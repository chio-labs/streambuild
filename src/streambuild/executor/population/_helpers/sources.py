"""Create passive managed sources and activate landing after downstream realization."""

from streambuild.compiler.compile.constants import RAW_TABLE_NAME_PREFIX
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
)
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource
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
    """Plan passive managed sources and deferred landing attachment without mutation."""

    preserved_names: list[str] = []
    created_names: list[str] = []
    landing_views: list[DesiredMaterializedView] = []
    realizations: list[PopulationRealization] = []
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    for desired_object in desired_state.objects:
        if not _is_managed_source_object(desired_object):
            continue
        if desired_object.name in existing_relation_names:
            preserved_names.append(desired_object.name)
            continue
        created_names.append(desired_object.name)
        if isinstance(desired_object, DesiredMaterializedView):
            landing_views.append(desired_object)
            continue
        realizations.append(
            PopulationRealization(
                resource=build_adapter_resource(desired_object),
                database=desired_object.key.database or default_database,
            )
        )
    return (
        PopulationSourcePreparation(
            preserved_relation_names=tuple(preserved_names),
            created_relation_names=tuple(created_names),
            landing_views=tuple(landing_views),
        ),
        tuple(realizations),
    )


def _is_managed_source_object(
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView,
) -> bool:
    if isinstance(desired_object, DesiredKafkaTable):
        return True
    if isinstance(desired_object, DesiredTable):
        return desired_object.name.startswith(RAW_TABLE_NAME_PREFIX)
    if isinstance(desired_object, DesiredMaterializedView):
        return desired_object.target_table_name.startswith(RAW_TABLE_NAME_PREFIX)
    return False
