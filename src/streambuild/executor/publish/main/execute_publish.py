"""Publish execution entrypoint."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import AdapterBindingReplacementRequest, AdapterMetadataState
from streambuild.executor.publish._helpers.metadata import build_publish_metadata_state
from streambuild.executor.publish._helpers.resolution import resolve_publish_deployment_id
from streambuild.executor.publish._helpers.views import build_publish_binding_request
from streambuild.executor.publish._helpers.workflow import assemble_publish_workflow
from streambuild.executor.publish.models import PublishedView, PublishRequest, PublishResult
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement


def execute_publish(*, request: PublishRequest, client: AdapterConnection) -> PublishResult:
    """Publish a staged deployment by creating or replacing stable logical views."""

    _validate_publish_capabilities(client)
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
    )
    statements: tuple[WarehouseStatement, ...] = assemble_publish_workflow(
        client=client,
        metadata_database=request.metadata_database,
        binding_request=binding_request,
        metadata_state=metadata_state,
    )
    _ = execute_warehouse_workflow(statements=statements, connection=client)
    return PublishResult(
        deployment_id=resolved_deployment_id,
        published_views=published_views,
        per_relation_atomic_replace=client.capabilities.per_relation_atomic_replace,
        graph_atomic_publish=client.capabilities.graph_atomic_publish,
    )


def _validate_publish_capabilities(client: AdapterConnection) -> None:
    if not client.capabilities.stable_logical_bindings:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support stable logical bindings"
        )
