from datetime import UTC, datetime, timedelta

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterPublishEventRecord,
    AdapterRelationCleanupRequest,
    AdapterRelationCleanupResult,
    InspectedManagedTableState,
)
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.planner.main.deployment_id_from_physical_name import (
    deployment_id_from_physical_name,
)
from streambuild.compiler.planner.main.is_deployment_physical_name import (
    is_deployment_physical_name,
)
from streambuild.compiler.planner.main.logical_name_from_physical_name import (
    logical_name_from_physical_name,
)
from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewCandidate,
    JanitorPreviewResult,
    JanitorRequest,
)


def execute_janitor_for_managed_table_state(
    *,
    request: JanitorRequest,
    client: AdapterConnection,
    managed_table_state: InspectedManagedTableState,
) -> JanitorPreviewResult | JanitorApplyResult:
    if request.apply:
        return _apply_janitor(
            client=client,
            database=request.database,
            metadata_database=request.metadata_database,
            retention_days=request.retention_days,
            managed_table_state=managed_table_state,
        )
    return _preview_janitor(
        client=client,
        database=request.database,
        metadata_database=request.metadata_database,
        retention_days=request.retention_days,
        managed_table_state=managed_table_state,
    )


def _preview_janitor(
    *,
    client: AdapterConnection,
    database: str,
    metadata_database: str,
    retention_days: int,
    managed_table_state: InspectedManagedTableState,
) -> JanitorPreviewResult:
    inventory: AdapterDeploymentInventory = client.load_deployment_inventory(metadata_database)
    published_at_by_deployment: dict[str, datetime] = _latest_publish_times(
        inventory.publish_events
    )
    active_deployment_ids: set[str] = {
        deployment_id_from_physical_name(binding.physical_name)
        for binding in managed_table_state.active_bindings
        if is_deployment_physical_name(binding.physical_name)
    }
    active_relation_names: frozenset[str] = frozenset(
        binding.physical_name for binding in managed_table_state.active_bindings
    )
    retention_cutoff: datetime = datetime.now(tz=UTC) - timedelta(days=retention_days)

    candidates: list[JanitorPreviewCandidate] = []
    deployment: AdapterDeploymentRecord
    for deployment in sorted(
        inventory.deployments,
        key=lambda value: value.created_at,
        reverse=True,
    ):
        logical_view_names: tuple[str, ...] = tuple(
            sorted(
                mapping.logical_key.name
                for mapping in deployment.prepared_object_mappings
                if mapping.logical_key.object_type == DESIRED_OBJECT_TYPE_TABLE
                and mapping.logical_key.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
            )
        )
        physical_object_names: tuple[str, ...] = tuple(
            sorted(mapping.physical_name for mapping in deployment.prepared_object_mappings)
        )
        if not _physical_mappings_are_safe(deployment):
            candidates.append(
                JanitorPreviewCandidate(
                    deployment_id=deployment.deployment_id,
                    created_at=deployment.created_at,
                    status=deployment.status,
                    logical_view_names=logical_view_names,
                    physical_object_names=physical_object_names,
                    deletable=False,
                    reason="physical mappings do not match deployment identity",
                )
            )
            continue
        if active_relation_names.intersection(physical_object_names):
            candidates.append(
                JanitorPreviewCandidate(
                    deployment_id=deployment.deployment_id,
                    created_at=deployment.created_at,
                    status=deployment.status,
                    logical_view_names=logical_view_names,
                    physical_object_names=physical_object_names,
                    deletable=False,
                    reason="contains currently active relation",
                )
            )
            continue
        if deployment.deployment_id in active_deployment_ids:
            candidates.append(
                JanitorPreviewCandidate(
                    deployment_id=deployment.deployment_id,
                    created_at=deployment.created_at,
                    status=deployment.status,
                    logical_view_names=logical_view_names,
                    physical_object_names=physical_object_names,
                    deletable=False,
                    reason="currently active",
                )
            )
            continue
        published_at: datetime | None = published_at_by_deployment.get(deployment.deployment_id)
        if published_at is not None and published_at >= retention_cutoff:
            candidates.append(
                JanitorPreviewCandidate(
                    deployment_id=deployment.deployment_id,
                    created_at=deployment.created_at,
                    status=deployment.status,
                    logical_view_names=logical_view_names,
                    physical_object_names=physical_object_names,
                    deletable=False,
                    reason=f"published within retention window ({retention_days} days)",
                )
            )
            continue
        reason: str = (
            f"published before retention window ({retention_days} days)"
            if published_at is not None
            else "stale unpublished deployment"
        )
        candidates.append(
            JanitorPreviewCandidate(
                deployment_id=deployment.deployment_id,
                created_at=deployment.created_at,
                status=deployment.status,
                logical_view_names=logical_view_names,
                physical_object_names=physical_object_names,
                deletable=True,
                reason=reason,
            )
        )

    return JanitorPreviewResult(
        database=database,
        retention_days=retention_days,
        candidates=tuple(candidates),
    )


def _apply_janitor(
    *,
    client: AdapterConnection,
    database: str,
    metadata_database: str,
    retention_days: int,
    managed_table_state: InspectedManagedTableState,
) -> JanitorApplyResult:
    preview_result: JanitorPreviewResult = _preview_janitor(
        client=client,
        database=database,
        metadata_database=metadata_database,
        retention_days=retention_days,
        managed_table_state=managed_table_state,
    )
    deleted_deployment_ids: list[str] = []
    requested_object_names: list[str] = []
    candidate: JanitorPreviewCandidate
    for candidate in preview_result.candidates:
        if not candidate.deletable:
            continue
        object_name: str
        for object_name in candidate.physical_object_names:
            requested_object_names.append(object_name)
        deleted_deployment_ids.append(candidate.deployment_id)

    cleanup_request: AdapterRelationCleanupRequest = AdapterRelationCleanupRequest(
        database=database,
        relation_names=tuple(requested_object_names),
    )
    refreshed_state: InspectedManagedTableState = client.inspect_managed_table_state(database)
    refreshed_active_names: frozenset[str] = frozenset(
        binding.physical_name for binding in refreshed_state.active_bindings
    )
    newly_active_names: frozenset[str] = refreshed_active_names.intersection(
        cleanup_request.relation_names
    )
    if newly_active_names:
        raise AdapterResultError(
            f"Refusing to clean relations that became active: {tuple(sorted(newly_active_names))!r}"
        )
    cleanup_result: AdapterRelationCleanupResult = client.cleanup_relations(cleanup_request)
    if cleanup_result.relation_names != cleanup_request.relation_names:
        raise AdapterResultError("Adapter cleanup result did not match requested relations")

    return JanitorApplyResult(
        database=database,
        retention_days=retention_days,
        deleted_deployment_ids=tuple(deleted_deployment_ids),
        deleted_object_names=cleanup_result.relation_names,
    )


def _physical_mappings_are_safe(deployment: AdapterDeploymentRecord) -> bool:
    return all(
        is_deployment_physical_name(mapping.physical_name)
        and deployment_id_from_physical_name(mapping.physical_name) == deployment.deployment_id
        and logical_name_from_physical_name(mapping.physical_name) == mapping.logical_key.name
        for mapping in deployment.prepared_object_mappings
    )


def _latest_publish_times(
    publish_events: tuple[AdapterPublishEventRecord, ...],
) -> dict[str, datetime]:
    latest_by_deployment: dict[str, datetime] = {}
    event: AdapterPublishEventRecord
    for event in publish_events:
        published_at: datetime = datetime.fromisoformat(
            event.published_at.replace(" ", "T")
        ).replace(tzinfo=UTC)
        current_latest: datetime | None = latest_by_deployment.get(event.deployment_id)
        if current_latest is None or published_at > current_latest:
            latest_by_deployment[event.deployment_id] = published_at
    return latest_by_deployment
