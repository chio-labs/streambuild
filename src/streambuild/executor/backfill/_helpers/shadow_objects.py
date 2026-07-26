"""Shadow object creation for backfill bootstrap execution."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
)
from streambuild.compiler.compile.constants import (
    RAW_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ObjectKey,
)
from streambuild.compiler.planner.constants import DEPLOYMENT_PHASE_PLAN
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource
from streambuild.compiler.planner.main.build_shadow_adapter_resource import (
    build_shadow_adapter_resource,
)
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.executor.backfill.exceptions import BackfillExecutionError


def create_shadow_objects(
    *,
    client: AdapterConnection,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    default_database: str,
    existing_relation_names: frozenset[str],
) -> None:
    """Create staged physical objects for the planned backfill deployment."""

    _ensure_live_landing_objects(
        client=client,
        desired_state=desired_state,
        default_database=default_database,
        existing_relation_names=existing_relation_names,
    )
    object_by_key: dict[ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView] = {
        object_.key: object_ for object_ in desired_state.objects
    }
    physical_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name
        for prepared in deployment_plan.prepared_shadow_objects
    }
    for target_key in _ordered_shadow_creation_keys(
        desired_state=desired_state, deployment_plan=deployment_plan
    ):
        desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = object_by_key[
            target_key
        ]
        database: str = desired_object.key.database or default_database
        if isinstance(desired_object, DesiredKafkaTable):
            raise BackfillExecutionError("Backfill bootstrap does not support shadow Kafka tables")
        resource: (
            AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView
        ) = build_shadow_adapter_resource(
            desired_object=desired_object,
            physical_name=physical_name_by_key[target_key],
            physical_name_by_key=physical_name_by_key,
        )
        client.realize_resource(
            resource=resource,
            database=database,
        )


def _ensure_live_landing_objects(
    *,
    client: AdapterConnection,
    desired_state: DesiredState,
    default_database: str,
    existing_relation_names: frozenset[str],
) -> None:
    existing_names: set[str] = set(existing_relation_names)
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        database: str = desired_object.key.database or default_database
        if isinstance(desired_object, DesiredKafkaTable):
            client.realize_resource(
                resource=build_adapter_resource(desired_object),
                database=database,
                if_not_exists=True,
            )
            existing_names.add(desired_object.name)
            continue
        if isinstance(desired_object, DesiredTable) and desired_object.name.startswith(
            RAW_TABLE_NAME_PREFIX
        ):
            if desired_object.name in existing_names:
                continue
            client.realize_resource(
                resource=build_adapter_resource(desired_object),
                database=database,
            )
            existing_names.add(desired_object.name)
            continue
        if isinstance(
            desired_object, DesiredMaterializedView
        ) and desired_object.target_table_name.startswith(RAW_TABLE_NAME_PREFIX):
            if desired_object.name in existing_names:
                continue
            client.realize_resource(
                resource=build_adapter_resource(desired_object),
                database=database,
            )
            existing_names.add(desired_object.name)


def _ordered_shadow_creation_keys(
    *,
    desired_state: DesiredState,
    deployment_plan: DeploymentPlan,
) -> tuple[ObjectKey, ...]:
    planned_keys: set[ObjectKey] = {
        step.target_key
        for step in deployment_plan.steps
        if step.phase == DEPLOYMENT_PHASE_PLAN and step.target_key is not None
    }
    object_by_key: dict[ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView] = {
        object_.key: object_ for object_ in desired_state.objects
    }
    ordered_keys: tuple[ObjectKey, ...] = ()
    visited_keys: frozenset[ObjectKey] = frozenset()

    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        ordered_keys, visited_keys = _visit_shadow_creation_key(
            key=desired_object.key,
            planned_keys=planned_keys,
            object_by_key=object_by_key,
            ordered_keys=ordered_keys,
            visited_keys=visited_keys,
        )
    return ordered_keys


def _visit_shadow_creation_key(
    *,
    key: ObjectKey,
    planned_keys: set[ObjectKey],
    object_by_key: dict[ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView],
    ordered_keys: tuple[ObjectKey, ...],
    visited_keys: frozenset[ObjectKey],
) -> tuple[tuple[ObjectKey, ...], frozenset[ObjectKey]]:
    if key not in planned_keys or key in visited_keys:
        return ordered_keys, visited_keys
    updated_visited_keys: frozenset[ObjectKey] = visited_keys | {key}
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = object_by_key[key]
    dependency_key: ObjectKey
    for dependency_key in desired_object.deps:
        ordered_keys, updated_visited_keys = _visit_shadow_creation_key(
            key=dependency_key,
            planned_keys=planned_keys,
            object_by_key=object_by_key,
            ordered_keys=ordered_keys,
            visited_keys=updated_visited_keys,
        )
    return (*ordered_keys, key), updated_visited_keys
