"""Inspect live and persisted inputs for actual-state assembly."""

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
from streambuild.compiler.actual_state.models import ActualStateInspection
from streambuild.compiler.compile.constants import TRANSFORM_TABLE_NAME_PREFIX
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ObjectKey,
    TableSpec,
)
from streambuild.compiler.metadata_state.models import ObjectStateRecord
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def load_actual_state_inspection(
    *,
    client: ClickHouseClient,
    desired_state: DesiredState,
    database: str,
) -> ActualStateInspection:
    """Load the live and persisted state required for actual-state assembly."""

    existing_names: frozenset[str] = frozenset(
        _load_existing_table_names(client=client, database=database)
    )
    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=database,
    )
    active_deployment_by_root: dict[ObjectKey, RootDeploymentInspection] = (
        _inspect_active_deployments(
            desired_state=desired_state,
            inspected_state=inspected_state,
        )
    )
    active_deployment_ids: tuple[str, ...] = _active_deployment_ids(active_deployment_by_root)
    records_by_deployment: dict[str, tuple[ObjectStateRecord, ...]] = (
        load_object_state_records_by_deployments(
            client=client,
            metadata_database=database,
            deployment_ids=active_deployment_ids,
        )
    )
    object_state_by_deployment_and_key: dict[tuple[str, ObjectKey], ObjectStateRecord] = (
        _index_object_state_records(
            deployment_ids=active_deployment_ids,
            records_by_deployment=records_by_deployment,
        )
    )
    transform_view_keys: tuple[ObjectKey, ...] = _transform_view_keys(desired_state)
    latest_object_state_by_key: dict[ObjectKey, ObjectStateRecord] = (
        load_latest_object_state_records_by_keys(
            client=client,
            metadata_database=database,
            keys=transform_view_keys,
        )
    )
    active_physical_names_by_logical_name: dict[str, str] = _index_active_physical_names(
        inspected_state
    )
    active_table_names: tuple[str, ...] = _active_table_names(
        desired_state=desired_state,
        active_deployment_by_root=active_deployment_by_root,
        active_physical_names_by_logical_name=active_physical_names_by_logical_name,
    )
    active_table_specs_by_name: dict[str, TableSpec] = _load_active_table_specs(
        client=client,
        database=database,
        table_names=active_table_names,
    )
    return ActualStateInspection(
        existing_names=existing_names,
        active_deployment_by_root=active_deployment_by_root,
        object_state_by_deployment_and_key=object_state_by_deployment_and_key,
        latest_object_state_by_key=latest_object_state_by_key,
        active_physical_names_by_logical_name=active_physical_names_by_logical_name,
        active_table_specs_by_name=active_table_specs_by_name,
    )


def _inspect_active_deployments(
    *,
    desired_state: DesiredState,
    inspected_state: InspectedManagedTableState,
) -> dict[ObjectKey, RootDeploymentInspection]:
    active_deployment_by_root: dict[ObjectKey, RootDeploymentInspection] = {}
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        if not isinstance(desired_object, DesiredTable):
            continue
        if not desired_object.name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
            continue
        active_deployment_by_root[desired_object.key] = inspect_root_deployment_state(
            inspected_state=inspected_state,
            root_key=desired_object.key,
        )
    return active_deployment_by_root


def _active_deployment_ids(
    active_deployment_by_root: dict[ObjectKey, RootDeploymentInspection],
) -> tuple[str, ...]:
    deployment_ids: set[str] = set()
    inspection: RootDeploymentInspection
    for inspection in active_deployment_by_root.values():
        if inspection.active_deployment_id is not None:
            deployment_ids.add(inspection.active_deployment_id)
    return tuple(sorted(deployment_ids))


def _index_object_state_records(
    *,
    deployment_ids: tuple[str, ...],
    records_by_deployment: dict[str, tuple[ObjectStateRecord, ...]],
) -> dict[tuple[str, ObjectKey], ObjectStateRecord]:
    records_by_deployment_and_key: dict[tuple[str, ObjectKey], ObjectStateRecord] = {}
    deployment_id: str
    record: ObjectStateRecord
    for deployment_id in deployment_ids:
        for record in records_by_deployment.get(deployment_id, ()):
            records_by_deployment_and_key[(record.deployment_id, record.key)] = record
    return records_by_deployment_and_key


def _transform_view_keys(desired_state: DesiredState) -> tuple[ObjectKey, ...]:
    keys: list[ObjectKey] = []
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        if not isinstance(desired_object, DesiredMaterializedView):
            continue
        if desired_object.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
            keys.append(desired_object.key)
    return tuple(keys)


def _index_active_physical_names(
    inspected_state: InspectedManagedTableState,
) -> dict[str, str]:
    names_by_logical_name: dict[str, str] = {}
    for binding in inspected_state.active_bindings:
        names_by_logical_name[binding.logical_name] = binding.physical_name
    return names_by_logical_name


def _active_table_names(
    *,
    desired_state: DesiredState,
    active_deployment_by_root: dict[ObjectKey, RootDeploymentInspection],
    active_physical_names_by_logical_name: dict[str, str],
) -> tuple[str, ...]:
    active_table_names: set[str] = set()
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        if not isinstance(desired_object, DesiredTable):
            continue
        if not desired_object.name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
            continue
        root_inspection: RootDeploymentInspection = active_deployment_by_root[desired_object.key]
        if root_inspection.state_kind != RootDeploymentStateKind.ACTIVE_VIEW_PRESENT:
            continue
        active_table_names.add(active_physical_names_by_logical_name[desired_object.name])
    return tuple(sorted(active_table_names))
