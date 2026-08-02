"""Realize one population plan through explicit physical mappings."""

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
    AdapterView,
)
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
    ObjectKey,
)
from streambuild.compiler.planner.main.build_shadow_adapter_resource import (
    build_shadow_adapter_resource,
)
from streambuild.executor.population.models import PopulationPlan, PopulationRealization


def plan_population_objects(
    *, plan: PopulationPlan, desired_state: DesiredState, default_database: str
) -> tuple[PopulationRealization, ...]:
    """Plan all mapped tables and views once in dependency order without mutation."""

    object_by_key: dict[
        ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    ] = {object_.key: object_ for object_ in desired_state.objects}
    physical_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name for prepared in plan.objects
    }
    realizations: list[PopulationRealization] = []
    target_key: ObjectKey
    for target_key in _ordered_creation_keys(
        desired_state=desired_state,
        planned_keys=frozenset(physical_name_by_key),
    ):
        desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView = (
            object_by_key[target_key]
        )
        if isinstance(desired_object, DesiredKafkaTable):
            continue
        resource: (
            AdapterManagedSource
            | AdapterTable
            | AdapterMaterializedView
            | AdapterView
            | AdapterStableView
        ) = build_shadow_adapter_resource(
            desired_object=desired_object,
            physical_name=physical_name_by_key[target_key],
            physical_name_by_key=physical_name_by_key,
        )
        realizations.append(
            PopulationRealization(
                resource=resource,
                database=desired_object.key.database or default_database,
            )
        )
    return tuple(realizations)


def _ordered_creation_keys(
    *, desired_state: DesiredState, planned_keys: frozenset[ObjectKey]
) -> tuple[ObjectKey, ...]:
    object_by_key: dict[
        ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    ] = {object_.key: object_ for object_ in desired_state.objects}
    ordered_keys: tuple[ObjectKey, ...] = ()
    visited_keys: frozenset[ObjectKey] = frozenset()
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    for desired_object in desired_state.objects:
        ordered_keys, visited_keys = _visit_creation_key(
            key=desired_object.key,
            planned_keys=planned_keys,
            object_by_key=object_by_key,
            ordered_keys=ordered_keys,
            visited_keys=visited_keys,
        )
    return ordered_keys


def _visit_creation_key(
    *,
    key: ObjectKey,
    planned_keys: frozenset[ObjectKey],
    object_by_key: dict[
        ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    ],
    ordered_keys: tuple[ObjectKey, ...],
    visited_keys: frozenset[ObjectKey],
) -> tuple[tuple[ObjectKey, ...], frozenset[ObjectKey]]:
    if key not in planned_keys or key in visited_keys:
        return ordered_keys, visited_keys
    updated_visited_keys: frozenset[ObjectKey] = visited_keys | {key}
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView = (
        object_by_key[key]
    )
    dependency_key: ObjectKey
    for dependency_key in desired_object.deps:
        ordered_keys, updated_visited_keys = _visit_creation_key(
            key=dependency_key,
            planned_keys=planned_keys,
            object_by_key=object_by_key,
            ordered_keys=ordered_keys,
            visited_keys=updated_visited_keys,
        )
    return (*ordered_keys, key), updated_visited_keys
