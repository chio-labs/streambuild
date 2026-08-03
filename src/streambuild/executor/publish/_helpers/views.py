"""Stable logical view creation helpers for publish."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import VIRTUAL_DEPLOYMENT_STATUS_INCOMPLETE
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterPreparedObjectMapping,
    AdapterStableBinding,
    AdapterStableBindingRemoval,
    InspectedManagedTableState,
    InspectedPhysicalTableCandidate,
)
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    DESIRED_OBJECT_TYPE_VIEW,
)
from streambuild.executor.publish.exceptions import PublishExecutionError


def build_publish_binding_request(
    *,
    client: AdapterConnection,
    metadata_database: str,
    default_database: str,
    deployment_id: str,
) -> AdapterBindingReplacementRequest:
    """Build validated stable bindings for a staged deployment."""

    inventory: AdapterDeploymentInventory = client.load_deployment_inventory(metadata_database)
    deployment: AdapterDeploymentRecord | None = next(
        (
            candidate
            for candidate in inventory.deployments
            if candidate.deployment_id == deployment_id
        ),
        None,
    )
    if deployment is None:
        return _publish_inspected_stable_views(
            client=client,
            default_database=default_database,
            deployment_id=deployment_id,
        )
    if deployment.status == VIRTUAL_DEPLOYMENT_STATUS_INCOMPLETE:
        raise PublishExecutionError(
            f"Deployment '{deployment_id}' is incomplete and cannot be published"
        )
    publish_mappings: tuple[AdapterPreparedObjectMapping, ...] = tuple(
        mapping
        for mapping in deployment.prepared_object_mappings
        if mapping.logical_key.object_type in {DESIRED_OBJECT_TYPE_TABLE, DESIRED_OBJECT_TYPE_VIEW}
    )
    if not publish_mappings:
        raise PublishExecutionError(
            f"Deployment '{deployment_id}' has no staged model relations to publish"
        )
    existing_names: frozenset[str] = client.load_catalog(default_database).relation_names()
    missing_names: tuple[str, ...] = tuple(
        sorted(
            mapping.physical_name
            for mapping in publish_mappings
            if mapping.physical_name not in existing_names
        )
    )
    if missing_names:
        raise PublishExecutionError(
            f"Deployment '{deployment_id}' is missing staged relations: {', '.join(missing_names)}"
        )
    ordered_mappings: tuple[AdapterPreparedObjectMapping, ...] = tuple(
        sorted(
            publish_mappings,
            key=lambda mapping: (
                mapping.logical_key.database or "",
                _published_view_kind_order(mapping.logical_key.object_type),
                mapping.logical_key.name,
            ),
        )
    )
    replacement_request: AdapterBindingReplacementRequest = AdapterBindingReplacementRequest(
        bindings=tuple(
            AdapterStableBinding(
                database=mapping.logical_key.database or default_database,
                logical_name=mapping.logical_key.name,
                physical_name=mapping.physical_name,
            )
            for mapping in ordered_mappings
        ),
        removals=_obsolete_binding_removals(
            client=client,
            inventory=inventory,
            current_mappings=ordered_mappings,
            default_database=default_database,
        ),
    )
    return replacement_request


def _publish_inspected_stable_views(
    *, client: AdapterConnection, default_database: str, deployment_id: str
) -> AdapterBindingReplacementRequest:
    candidates: tuple[InspectedPhysicalTableCandidate, ...] = tuple(
        candidate
        for candidate in client.inspect_managed_table_state(default_database).physical_candidates
        if candidate.physical_name.endswith(f"__{deployment_id}")
        and candidate.object_type in {DESIRED_OBJECT_TYPE_TABLE, DESIRED_OBJECT_TYPE_VIEW}
    )
    if not candidates:
        raise PublishExecutionError(
            f"Deployment '{deployment_id}' has no staged model relations to publish"
        )
    existing_names: frozenset[str] = client.load_catalog(default_database).relation_names()
    missing_names: tuple[str, ...] = tuple(
        sorted(
            candidate.physical_name
            for candidate in candidates
            if candidate.physical_name not in existing_names
        )
    )
    if missing_names:
        raise PublishExecutionError(
            f"Deployment '{deployment_id}' is missing staged relations: {', '.join(missing_names)}"
        )
    ordered_candidates: tuple[InspectedPhysicalTableCandidate, ...] = tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.database,
                _published_view_kind_order(candidate.object_type),
                candidate.logical_name,
            ),
        )
    )
    return AdapterBindingReplacementRequest(
        bindings=tuple(
            AdapterStableBinding(
                database=candidate.database,
                logical_name=candidate.logical_name,
                physical_name=candidate.physical_name,
            )
            for candidate in ordered_candidates
        )
    )


def _published_view_kind_order(object_type: str) -> int:
    if object_type == DESIRED_OBJECT_TYPE_TABLE:
        return 0
    return 1


def _obsolete_binding_removals(
    *,
    client: AdapterConnection,
    inventory: AdapterDeploymentInventory,
    current_mappings: tuple[AdapterPreparedObjectMapping, ...],
    default_database: str,
) -> tuple[AdapterStableBindingRemoval, ...]:
    current_names: frozenset[tuple[str, str]] = frozenset(
        (mapping.logical_key.database or default_database, mapping.logical_key.name)
        for mapping in current_mappings
    )
    current_model_names: frozenset[str] = frozenset(
        mapping.logical_model_name for mapping in current_mappings
    )
    published_names_by_deployment: dict[str, set[str]] = {}
    for event in inventory.publish_events:
        published_names_by_deployment.setdefault(event.deployment_id, set()).update(
            event.logical_view_names
        )
    historical_bindings: set[tuple[str, str, str]] = set()
    for deployment in inventory.deployments:
        published_names: set[str] = published_names_by_deployment.get(
            deployment.deployment_id, set()
        )
        for mapping in deployment.prepared_object_mappings:
            binding_name: tuple[str, str] = (
                mapping.logical_key.database or default_database,
                mapping.logical_key.name,
            )
            if (
                mapping.logical_model_name in current_model_names
                and mapping.logical_key.name in published_names
                and binding_name not in current_names
            ):
                historical_bindings.add((*binding_name, mapping.physical_name))
    inspected_state: InspectedManagedTableState = client.inspect_managed_table_state(
        default_database
    )
    active_bindings: set[tuple[str, str, str]] = {
        (binding.database, binding.logical_name, binding.physical_name)
        for binding in inspected_state.active_bindings
    }
    return tuple(
        AdapterStableBindingRemoval(database=database, logical_name=logical_name)
        for database, logical_name, physical_name in sorted(historical_bindings)
        if (database, logical_name, physical_name) in active_bindings
    )
