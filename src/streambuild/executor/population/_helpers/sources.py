"""Create passive managed sources and activate landing after downstream realization."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.constants import RAW_TABLE_NAME_PREFIX
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
)
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource
from streambuild.executor.population.models import PopulationSourcePreparation


def prepare_population_sources_impl(
    *,
    client: AdapterConnection,
    desired_state: DesiredState,
    default_database: str,
    existing_relation_names: frozenset[str],
) -> PopulationSourcePreparation:
    """Create absent Kafka/raw resources while leaving absent landing views detached."""

    preserved_names: list[str] = []
    created_names: list[str] = []
    landing_views: list[DesiredMaterializedView] = []
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
        client.realize_resource(
            resource=build_adapter_resource(desired_object),
            database=desired_object.key.database or default_database,
            if_not_exists=True,
        )
    return PopulationSourcePreparation(
        preserved_relation_names=tuple(preserved_names),
        created_relation_names=tuple(created_names),
        landing_views=tuple(landing_views),
    )


def activate_population_sources(
    *,
    client: AdapterConnection,
    preparation: PopulationSourcePreparation,
    default_database: str,
) -> None:
    """Attach every newly required landing view after downstream resources are live."""

    landing_view: DesiredMaterializedView
    for landing_view in preparation.landing_views:
        client.realize_resource(
            resource=build_adapter_resource(landing_view),
            database=landing_view.key.database or default_database,
            if_not_exists=True,
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
