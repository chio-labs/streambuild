"""Publish execution entrypoint."""

from uuid import uuid4

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterMetadataState,
    AdapterOwnedResourceEvent,
    AdapterOwnedResourceSnapshot,
)
from streambuild.executor.promotion._helpers.metadata import build_publish_metadata_state
from streambuild.executor.promotion._helpers.resolution import resolve_publish_deployment_id
from streambuild.executor.promotion._helpers.views import build_publish_binding_request
from streambuild.executor.promotion._helpers.workflow import assemble_publish_workflow
from streambuild.executor.promotion.models import PublishedView, PublishRequest, PublishResult
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.main.target_mutation_lock import target_mutation_lock
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import WorkflowEventEmitter


def execute_publish(
    *,
    request: PublishRequest,
    client: AdapterConnection,
    emitter: WorkflowEventEmitter | None = None,
) -> PublishResult:
    """Publish a staged deployment by creating or replacing stable logical views."""

    _validate_publish_capabilities(client)
    with target_mutation_lock(connection=client, database=request.default_database):
        resolved_deployment_id: str = resolve_publish_deployment_id(
            client=client,
            metadata_database=request.metadata_database,
            default_database=request.default_database,
            deployment_id=request.deployment_id,
        )
        binding_request: AdapterBindingReplacementRequest = build_publish_binding_request(
            client=client,
            metadata_database=request.metadata_database,
            default_database=request.default_database,
            deployment_id=resolved_deployment_id,
        )
        published_views: tuple[PublishedView, ...] = tuple(
            PublishedView(
                view_name=binding.logical_name,
                target_table_name=binding.physical_name,
            )
            for binding in binding_request.bindings
        )
        published_at: str = client.capture_warehouse_timestamp()
        metadata_state: AdapterMetadataState = build_publish_metadata_state(
            deployment_id=resolved_deployment_id,
            published_at=published_at,
            published_views=published_views,
            database=request.default_database,
            operation=request.operation,
            previous_deployment_id=request.previous_deployment_id,
        )
        ownership_events: tuple[AdapterOwnedResourceEvent, ...] = _binding_ownership_events(
            request=request,
            client=client,
            binding_request=binding_request,
        )
        statements: tuple[WarehouseStatement, ...] = assemble_publish_workflow(
            client=client,
            metadata_database=request.metadata_database,
            binding_request=binding_request,
            metadata_state=metadata_state,
            ownership_events=ownership_events,
        )
        _ = execute_warehouse_workflow(statements=statements, connection=client, emitter=emitter)
        return PublishResult(
            deployment_id=resolved_deployment_id,
            published_views=published_views,
            per_relation_atomic_replace=client.capabilities.per_relation_atomic_replace,
            graph_atomic_publish=client.capabilities.graph_atomic_publish,
            operation=request.operation,
            previous_deployment_id=request.previous_deployment_id,
        )


def _validate_publish_capabilities(client: AdapterConnection) -> None:
    if not client.capabilities.stable_logical_bindings:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support stable logical bindings"
        )


def _binding_ownership_events(
    *,
    request: PublishRequest,
    client: AdapterConnection,
    binding_request: AdapterBindingReplacementRequest,
) -> tuple[AdapterOwnedResourceEvent, ...]:
    snapshot: AdapterOwnedResourceSnapshot = client.load_owned_resources(
        database=request.metadata_database,
        target_database=request.default_database,
    )
    by_name: dict[tuple[str, str], AdapterOwnedResourceEvent] = {
        (event.resource_database, event.resource_name): event for event in snapshot.resources
    }
    events: list[AdapterOwnedResourceEvent] = []
    for binding in binding_request.bindings:
        physical: AdapterOwnedResourceEvent | None = by_name.get(
            (binding.database, binding.physical_name)
        )
        events.append(
            AdapterOwnedResourceEvent(
                event_id=f"owned_{uuid4().hex}",
                event_type="owned",
                target_database=request.default_database,
                resource_database=binding.database,
                resource_name=binding.logical_name,
                resource_kind="view",
                pipeline_name="" if physical is None else physical.pipeline_name,
                logical_resource_type="model",
                logical_resource_name=(
                    binding.logical_name if physical is None else physical.logical_resource_name
                ),
                resource_role="stable_binding",
            )
        )
    for removal in binding_request.removals:
        existing: AdapterOwnedResourceEvent | None = by_name.get(
            (removal.database, removal.logical_name)
        )
        events.append(
            AdapterOwnedResourceEvent(
                event_id=f"dropped_{uuid4().hex}",
                event_type="dropped",
                target_database=request.default_database,
                resource_database=removal.database,
                resource_name=removal.logical_name,
                resource_kind="view",
                pipeline_name="" if existing is None else existing.pipeline_name,
                logical_resource_type="model",
                logical_resource_name=(
                    removal.logical_name if existing is None else existing.logical_resource_name
                ),
                resource_role="stable_binding",
                catalog_fingerprint=(None if existing is None else existing.catalog_fingerprint),
            )
        )
    return tuple(events)
