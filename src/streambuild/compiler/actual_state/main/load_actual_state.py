"""Load actual warehouse state for the managed objects of a pipeline."""

from streambuild.clickhouse.inspect.main.inspect_managed_table_state import (
    inspect_managed_table_state,
)
from streambuild.clickhouse.inspect.main.inspect_root_deployment_state import (
    inspect_root_deployment_state,
)
from streambuild.clickhouse.inspect.models import (
    InspectedManagedTableState,
    RootDeploymentInspection,
)
from streambuild.clickhouse.inspect.types import RootDeploymentStateKind
from streambuild.compiler.actual_state._helpers.load import (
    _load_active_table_specs,
    _load_existing_table_names,
)
from streambuild.compiler.actual_state._helpers.metadata import (
    load_latest_object_state_records_by_keys,
    load_object_state_records_by_deployments,
)
from streambuild.compiler.actual_state.main._build_actual_state import build_actual_state
from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualTable,
)
from streambuild.compiler.compile.constants import (
    MATERIALIZED_VIEW_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.metadata_state.models import ObjectStateRecord
from streambuild.executor.reconcile.constants import RECONCILE_DEPLOYMENT_ID_PREFIX
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def load_actual_state(
    *,
    client: ClickHouseClient,
    desired_state: DesiredState,
    database: str,
) -> ActualState:
    """Load the current active actual state from ClickHouse inspection."""

    existing_names: set[str] = _load_existing_table_names(client=client, database=database)
    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=database,
    )
    active_deployment_by_root: dict[ObjectKey, RootDeploymentInspection] = {
        object_.key: inspect_root_deployment_state(
            inspected_state=inspected_state,
            root_key=object_.key,
        )
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
        and object_.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
    }
    active_deployment_ids: tuple[str, ...] = tuple(
        sorted(
            {
                inspection.active_deployment_id
                for inspection in active_deployment_by_root.values()
                if inspection.active_deployment_id is not None
            }
        )
    )
    object_state_records_by_deployment: dict[str, tuple[ObjectStateRecord, ...]] = (
        load_object_state_records_by_deployments(
            client=client,
            metadata_database=database,
            deployment_ids=active_deployment_ids,
        )
    )
    object_state_by_deployment_and_key: dict[tuple[str, ObjectKey], ObjectStateRecord] = {
        (record.deployment_id, record.key): record
        for deployment_id in active_deployment_ids
        for record in object_state_records_by_deployment.get(deployment_id, ())
    }
    latest_object_state_by_key: dict[ObjectKey, ObjectStateRecord] = (
        load_latest_object_state_records_by_keys(
            client=client,
            metadata_database=database,
            keys=tuple(
                object_.key
                for object_ in desired_state.objects
                if isinstance(object_, DesiredMaterializedView)
                and object_.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
            ),
        )
    )
    active_physical_names_by_logical_name: dict[str, str] = {
        binding.logical_name: binding.physical_name for binding in inspected_state.active_bindings
    }
    active_table_names: tuple[str, ...] = tuple(
        sorted(
            {
                active_physical_names_by_logical_name[desired_object.name]
                for desired_object in desired_state.objects
                if isinstance(desired_object, DesiredTable)
                and desired_object.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
                and active_deployment_by_root[desired_object.key].state_kind
                == RootDeploymentStateKind.ACTIVE_VIEW_PRESENT
            }
        )
    )
    active_table_specs_by_name: dict[str, TableSpec] = _load_active_table_specs(
        client=client,
        database=database,
        table_names=active_table_names,
    )

    actual_objects: list[ActualKafkaTable | ActualTable | ActualMaterializedView] = []
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        if isinstance(desired_object, DesiredKafkaTable):
            if desired_object.name not in existing_names:
                continue
            actual_objects.append(
                ActualKafkaTable(
                    key=desired_object.key,
                    spec=KafkaTableSpec(
                        columns=desired_object.columns,
                        kafka=desired_object.kafka,
                    ),
                )
            )
            continue

        if isinstance(desired_object, DesiredTable):
            if desired_object.name.startswith(RAW_TABLE_NAME_PREFIX):
                if desired_object.name not in existing_names:
                    continue
                actual_objects.append(
                    ActualTable(
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
                )
                continue

            root_inspection: RootDeploymentInspection = active_deployment_by_root[
                desired_object.key
            ]
            if root_inspection.state_kind != RootDeploymentStateKind.ACTIVE_VIEW_PRESENT:
                continue
            active_physical_name: str = active_physical_names_by_logical_name[desired_object.name]
            actual_objects.append(
                ActualTable(
                    key=desired_object.key,
                    spec=active_table_specs_by_name[active_physical_name],
                )
            )
            continue

        if desired_object.name not in existing_names and not desired_object.name.startswith(
            MATERIALIZED_VIEW_NAME_PREFIX
        ):
            continue
        actual_query: str = desired_object.query
        if desired_object.name.startswith(
            MATERIALIZED_VIEW_NAME_PREFIX
        ) and desired_object.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
            root_key: ObjectKey = next(
                object_.key
                for object_ in desired_state.objects
                if isinstance(object_, DesiredTable)
                and object_.name == desired_object.target_table_name
            )
            root_inspection = active_deployment_by_root[root_key]
            if root_inspection.state_kind != RootDeploymentStateKind.ACTIVE_VIEW_PRESENT:
                continue
            if root_inspection.active_deployment_id is not None:
                object_state_record: ObjectStateRecord | None = (
                    object_state_by_deployment_and_key.get(
                        (root_inspection.active_deployment_id, desired_object.key)
                    )
                )
                if (
                    object_state_record is not None
                    and object_state_record.normalized_query is not None
                ):
                    actual_query = object_state_record.normalized_query
            latest_object_state_record: ObjectStateRecord | None = latest_object_state_by_key.get(
                desired_object.key
            )
            if (
                latest_object_state_record is not None
                and latest_object_state_record.deployment_id.startswith(
                    RECONCILE_DEPLOYMENT_ID_PREFIX
                )
                and latest_object_state_record.normalized_query is not None
            ):
                actual_query = latest_object_state_record.normalized_query
        elif desired_object.name.startswith(
            MATERIALIZED_VIEW_NAME_PREFIX
        ) and desired_object.target_table_name.startswith(RAW_TABLE_NAME_PREFIX):
            if desired_object.name not in existing_names:
                continue
            actual_query = desired_object.query
        elif desired_object.name not in existing_names:
            continue
        actual_objects.append(
            ActualMaterializedView(
                key=desired_object.key,
                spec=MaterializedViewSpec(
                    source_table_name=desired_object.source_table_name,
                    target_table_name=desired_object.target_table_name,
                    query=actual_query,
                ),
            )
        )

    return build_actual_state(tuple(actual_objects))
