"""Assemble actual objects from desired objects and inspected state."""

from streambuild.compiler.compile.constants import (
    MATERIALIZED_VIEW_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
    ViewSpec,
)
from streambuild.compiler.planner.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualStateInspection,
    ActualTable,
    ActualView,
    ObjectStateRecord,
    RootDeploymentInspection,
)
from streambuild.compiler.planner.types import RootDeploymentStateKind
from streambuild.executor.reconcile.constants import RECONCILE_DEPLOYMENT_ID_PREFIX


def build_inspected_actual_objects(
    *,
    desired_state: DesiredState,
    inspection: ActualStateInspection,
) -> tuple[ActualKafkaTable | ActualTable | ActualMaterializedView | ActualView, ...]:
    """Build actual objects corresponding to the desired object graph."""

    actual_objects: list[ActualKafkaTable | ActualTable | ActualMaterializedView | ActualView] = []
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    for desired_object in desired_state.objects:
        actual_object: ActualKafkaTable | ActualTable | ActualMaterializedView | ActualView | None
        if isinstance(desired_object, DesiredKafkaTable):
            actual_object = _build_actual_kafka_table(
                desired_object=desired_object,
                inspection=inspection,
            )
        elif isinstance(desired_object, DesiredTable):
            actual_object = _build_actual_table(
                desired_object=desired_object,
                inspection=inspection,
            )
        elif isinstance(desired_object, DesiredMaterializedView):
            actual_object = _build_actual_materialized_view(
                desired_object=desired_object,
                desired_state=desired_state,
                inspection=inspection,
            )
        else:
            actual_object = _build_actual_view(
                desired_object=desired_object,
                inspection=inspection,
            )
        if actual_object is not None:
            actual_objects.append(actual_object)
    return tuple(actual_objects)


def _build_actual_kafka_table(
    *,
    desired_object: DesiredKafkaTable,
    inspection: ActualStateInspection,
) -> ActualKafkaTable | None:
    if desired_object.name not in inspection.existing_names:
        return None
    return ActualKafkaTable(
        key=desired_object.key,
        spec=KafkaTableSpec(
            columns=desired_object.columns,
            kafka=desired_object.kafka,
        ),
    )


def _build_actual_table(
    *,
    desired_object: DesiredTable,
    inspection: ActualStateInspection,
) -> ActualTable | None:
    if desired_object.name.startswith(RAW_TABLE_NAME_PREFIX):
        if desired_object.name not in inspection.existing_names:
            return None
        return ActualTable(
            key=desired_object.key,
            spec=TableSpec(
                columns=desired_object.columns,
                storage=TableStorage(
                    engine=desired_object.engine,
                    order_by=desired_object.order_by,
                    partition_by=desired_object.partition_by,
                    ttl=desired_object.ttl,
                    settings=desired_object.settings,
                ),
            ),
        )

    root_inspection: RootDeploymentInspection = inspection.active_deployment_by_root[
        desired_object.key
    ]
    if root_inspection.state_kind != RootDeploymentStateKind.ACTIVE_VIEW_PRESENT:
        return None
    active_physical_name: str = inspection.active_physical_names_by_logical_name[
        desired_object.name
    ]
    return ActualTable(
        key=desired_object.key,
        spec=inspection.active_table_specs_by_name[active_physical_name],
    )


def _build_actual_materialized_view(
    *,
    desired_object: DesiredMaterializedView,
    desired_state: DesiredState,
    inspection: ActualStateInspection,
) -> ActualMaterializedView | None:
    is_managed_view: bool = desired_object.name.startswith(MATERIALIZED_VIEW_NAME_PREFIX)
    if desired_object.name not in inspection.existing_names and not is_managed_view:
        return None

    actual_query: str = desired_object.query
    model_table_names: frozenset[str] = frozenset(
        object_.name
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable) and not object_.name.startswith(RAW_TABLE_NAME_PREFIX)
    )
    if is_managed_view and desired_object.target_table_name in model_table_names:
        root_key: ObjectKey = _transform_root_key(
            desired_state=desired_state,
            target_table_name=desired_object.target_table_name,
        )
        root_inspection: RootDeploymentInspection = inspection.active_deployment_by_root[root_key]
        if root_inspection.state_kind != RootDeploymentStateKind.ACTIVE_VIEW_PRESENT:
            return None
        actual_query = _active_deployment_query(
            desired_object=desired_object,
            root_inspection=root_inspection,
            inspection=inspection,
        )
        actual_query = _latest_reconcile_query(
            desired_object=desired_object,
            fallback_query=actual_query,
            inspection=inspection,
        )
    elif is_managed_view and desired_object.target_table_name.startswith(RAW_TABLE_NAME_PREFIX):
        if desired_object.name not in inspection.existing_names:
            return None
    elif desired_object.name not in inspection.existing_names:
        return None

    return ActualMaterializedView(
        key=desired_object.key,
        spec=MaterializedViewSpec(
            source_table_name=desired_object.source_table_name,
            target_table_name=desired_object.target_table_name,
            query=actual_query,
            database_template=actual_query,
        ),
    )


def _build_actual_view(
    *,
    desired_object: DesiredView,
    inspection: ActualStateInspection,
) -> ActualView | None:
    root_inspection: RootDeploymentInspection | None = inspection.active_deployment_by_root.get(
        desired_object.key
    )
    if (
        root_inspection is None
        or root_inspection.state_kind != RootDeploymentStateKind.ACTIVE_VIEW_PRESENT
        or root_inspection.active_deployment_id is None
    ):
        return None
    object_state_record: ObjectStateRecord | None = (
        inspection.object_state_by_deployment_and_key.get(
            (root_inspection.active_deployment_id, desired_object.key)
        )
    )
    if object_state_record is None or object_state_record.normalized_query is None:
        return None
    return ActualView(
        key=desired_object.key,
        spec=ViewSpec(
            query=object_state_record.normalized_query,
            database_template=object_state_record.normalized_query,
        ),
    )


def _transform_root_key(*, desired_state: DesiredState, target_table_name: str) -> ObjectKey:
    return next(
        desired_object.key
        for desired_object in desired_state.objects
        if isinstance(desired_object, DesiredTable) and desired_object.name == target_table_name
    )


def _active_deployment_query(
    *,
    desired_object: DesiredMaterializedView,
    root_inspection: RootDeploymentInspection,
    inspection: ActualStateInspection,
) -> str:
    if root_inspection.active_deployment_id is None:
        return desired_object.query
    object_state_record: ObjectStateRecord | None = (
        inspection.object_state_by_deployment_and_key.get(
            (root_inspection.active_deployment_id, desired_object.key)
        )
    )
    if object_state_record is None or object_state_record.normalized_query is None:
        return desired_object.query
    return object_state_record.normalized_query


def _latest_reconcile_query(
    *,
    desired_object: DesiredMaterializedView,
    fallback_query: str,
    inspection: ActualStateInspection,
) -> str:
    latest_record: ObjectStateRecord | None = inspection.latest_object_state_by_key.get(
        desired_object.key
    )
    if latest_record is None:
        return fallback_query
    if not latest_record.deployment_id.startswith(RECONCILE_DEPLOYMENT_ID_PREFIX):
        return fallback_query
    if latest_record.normalized_query is None:
        return fallback_query
    return latest_record.normalized_query
