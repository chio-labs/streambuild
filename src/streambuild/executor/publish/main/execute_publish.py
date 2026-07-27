"""Publish execution entrypoint."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import AdapterBindingReplacementResult
from streambuild.executor.publish._helpers.metadata import persist_publish_event
from streambuild.executor.publish._helpers.resolution import resolve_publish_deployment_id
from streambuild.executor.publish._helpers.views import publish_stable_views
from streambuild.executor.publish.models import PublishedView, PublishRequest, PublishResult


def execute_publish(*, request: PublishRequest, client: AdapterConnection) -> PublishResult:
    """Publish a staged deployment by creating or replacing stable logical views."""

    _validate_publish_capabilities(client)
    resolved_deployment_id: str = resolve_publish_deployment_id(
        client=client,
        metadata_database=request.metadata_database,
        default_database=request.default_database,
        deployment_id=request.deployment_id,
    )
    binding_result: AdapterBindingReplacementResult = publish_stable_views(
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
        for binding in binding_result.bindings
    )
    persist_publish_event(
        client=client,
        metadata_database=request.metadata_database,
        deployment_id=resolved_deployment_id,
        published_views=published_views,
    )
    return PublishResult(
        deployment_id=resolved_deployment_id,
        published_views=published_views,
        per_relation_atomic_replace=binding_result.per_relation_atomic_replace,
        graph_atomic_publish=binding_result.graph_atomic_publish,
    )


def _validate_publish_capabilities(client: AdapterConnection) -> None:
    if not client.capabilities.stable_logical_bindings:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support stable logical bindings"
        )
