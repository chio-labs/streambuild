"""Resolve rollback publications from authoritative metadata and live bindings."""

from datetime import UTC, datetime

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterPublishEventRecord,
    AdapterStableBinding,
    InspectedActiveTableBinding,
    InspectedManagedTableState,
)
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    DESIRED_OBJECT_TYPE_VIEW,
)
from streambuild.executor.promotion.exceptions import PublishExecutionError
from streambuild.executor.promotion.models import RollbackPlan, RollbackRequest


def resolve_rollback_plan(*, request: RollbackRequest, client: AdapterConnection) -> RollbackPlan:
    """Resolve the active publication and requested retained rollback target."""

    inventory: AdapterDeploymentInventory = client.load_deployment_inventory(
        request.metadata_database
    )
    managed_state: InspectedManagedTableState = client.inspect_managed_table_state(
        request.default_database
    )
    current_event: AdapterPublishEventRecord = _current_publish_event(
        events=inventory.publish_events,
        active_bindings=managed_state.active_bindings,
    )
    target_event: AdapterPublishEventRecord = (
        _previous_publish_event(events=inventory.publish_events, current_event=current_event)
        if request.previous
        else _explicit_publish_event(
            events=inventory.publish_events,
            deployment_id=request.deployment_id or "",
            current_event=current_event,
        )
    )
    deployment_by_id: dict[str, AdapterDeploymentRecord] = {
        deployment.deployment_id: deployment for deployment in inventory.deployments
    }
    target_deployment: AdapterDeploymentRecord | None = deployment_by_id.get(
        target_event.deployment_id
    )
    if target_deployment is None:
        raise PublishExecutionError(
            f"Rollback target deployment '{target_event.deployment_id}' is missing "
            "deployment metadata"
        )
    expected_bindings: tuple[AdapterStableBinding, ...] = tuple(
        AdapterStableBinding(
            database=mapping.logical_key.database or request.default_database,
            logical_name=mapping.logical_key.name,
            physical_name=mapping.physical_name,
        )
        for mapping in target_deployment.prepared_object_mappings
        if mapping.logical_key.object_type in {DESIRED_OBJECT_TYPE_TABLE, DESIRED_OBJECT_TYPE_VIEW}
    )
    if _binding_identity(target_event.bindings) != _binding_identity(expected_bindings):
        raise PublishExecutionError(
            f"Rollback target deployment '{target_event.deployment_id}' publication bindings "
            "do not match its deployment metadata"
        )
    return RollbackPlan(
        current_deployment_id=current_event.deployment_id,
        target_deployment_id=target_event.deployment_id,
        logical_view_names=tuple(
            sorted(
                mapping.logical_key.name
                for mapping in target_deployment.prepared_object_mappings
                if mapping.logical_key.object_type
                in {DESIRED_OBJECT_TYPE_TABLE, DESIRED_OBJECT_TYPE_VIEW}
            )
        ),
    )


def _current_publish_event(
    *,
    events: tuple[AdapterPublishEventRecord, ...],
    active_bindings: tuple[InspectedActiveTableBinding, ...],
) -> AdapterPublishEventRecord:
    if not active_bindings:
        raise PublishExecutionError("Rollback requires an active published deployment")
    active_identity: tuple[tuple[str, str, str], ...] = tuple(
        sorted(
            (binding.database, binding.logical_name, binding.physical_name)
            for binding in active_bindings
        )
    )
    matching_events: tuple[AdapterPublishEventRecord, ...] = tuple(
        event for event in events if _binding_identity(event.bindings) == active_identity
    )
    if not matching_events:
        raise PublishExecutionError(
            "Active bindings do not match a complete publication; repair the target before rollback"
        )
    return max(matching_events, key=_event_rank)


def _previous_publish_event(
    *,
    events: tuple[AdapterPublishEventRecord, ...],
    current_event: AdapterPublishEventRecord,
) -> AdapterPublishEventRecord:
    current_rank: tuple[datetime, str] = _event_rank(current_event)
    current_identity: tuple[tuple[str, str, str], ...] = _binding_identity(current_event.bindings)
    previous_events: tuple[AdapterPublishEventRecord, ...] = tuple(
        sorted(
            (
                event
                for event in events
                if _event_rank(event) < current_rank
                and _binding_identity(event.bindings) != current_identity
            ),
            key=_event_rank,
            reverse=True,
        )
    )
    if not previous_events:
        raise PublishExecutionError("No previous published deployment is available for rollback")
    return previous_events[0]


def _explicit_publish_event(
    *,
    events: tuple[AdapterPublishEventRecord, ...],
    deployment_id: str,
    current_event: AdapterPublishEventRecord,
) -> AdapterPublishEventRecord:
    if deployment_id == current_event.deployment_id:
        raise PublishExecutionError(f"Deployment '{deployment_id}' is already active")
    matching_events: tuple[AdapterPublishEventRecord, ...] = tuple(
        event for event in events if event.deployment_id == deployment_id
    )
    if not matching_events:
        raise PublishExecutionError(
            f"Deployment '{deployment_id}' has no successful publication to roll back to"
        )
    return max(matching_events, key=_event_rank)


def _binding_identity(
    bindings: tuple[AdapterStableBinding, ...],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (binding.database, binding.logical_name, binding.physical_name) for binding in bindings
        )
    )


def _event_rank(event: AdapterPublishEventRecord) -> tuple[datetime, str]:
    published_at: datetime = datetime.fromisoformat(event.published_at.replace(" ", "T"))
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    return published_at, event.publication_id or event.deployment_id
