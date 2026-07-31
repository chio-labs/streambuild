from datetime import UTC, datetime, timedelta

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterPublishEventRecord,
    AdapterRelationCleanupRequest,
    AdapterRelationCleanupResult,
    AdapterStableBindingRemoval,
    InspectedManagedTableState,
)
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    DESIRED_OBJECT_TYPE_VIEW,
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
    active_relation_names, _obsolete_removals = _binding_activity(
        inventory=inventory,
        managed_table_state=managed_table_state,
    )
    active_deployment_ids: set[str] = {
        deployment_id_from_physical_name(binding.physical_name)
        for binding in managed_table_state.active_bindings
        if binding.physical_name in active_relation_names
        and is_deployment_physical_name(binding.physical_name)
    }
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
                if mapping.logical_key.object_type
                in {DESIRED_OBJECT_TYPE_TABLE, DESIRED_OBJECT_TYPE_VIEW}
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
    inventory: AdapterDeploymentInventory = client.load_deployment_inventory(metadata_database)
    _active_relation_names, obsolete_removals = _binding_activity(
        inventory=inventory,
        managed_table_state=managed_table_state,
    )
    replacement_result: AdapterBindingReplacementResult = client.replace_stable_bindings(
        AdapterBindingReplacementRequest(bindings=(), removals=obsolete_removals)
    )
    if replacement_result.removals != obsolete_removals:
        raise AdapterResultError("Adapter did not remove the requested obsolete bindings")
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


def _binding_activity(
    *,
    inventory: AdapterDeploymentInventory,
    managed_table_state: InspectedManagedTableState,
) -> tuple[frozenset[str], tuple[AdapterStableBindingRemoval, ...]]:
    published_names_by_deployment: dict[str, set[str]] = {}
    published_rank_by_deployment: dict[str, tuple[datetime, str]] = {}
    for event in inventory.publish_events:
        published_names_by_deployment.setdefault(event.deployment_id, set()).update(
            event.logical_view_names
        )
        published_at: datetime = datetime.fromisoformat(
            event.published_at.replace(" ", "T")
        ).replace(tzinfo=UTC)
        rank: tuple[datetime, str] = (published_at, event.deployment_id)
        current_rank: tuple[datetime, str] | None = published_rank_by_deployment.get(
            event.deployment_id
        )
        if current_rank is None or rank > current_rank:
            published_rank_by_deployment[event.deployment_id] = rank
    known_physical_names: set[str] = set()
    latest_by_model_name: dict[str, tuple[tuple[datetime, str], str]] = {}
    for deployment in inventory.deployments:
        rank: tuple[datetime, str] | None = published_rank_by_deployment.get(
            deployment.deployment_id
        )
        published_names: set[str] = published_names_by_deployment.get(
            deployment.deployment_id, set()
        )
        if rank is None:
            continue
        for mapping in deployment.prepared_object_mappings:
            if mapping.logical_key.name not in published_names:
                continue
            known_physical_names.add(mapping.physical_name)
            current: tuple[tuple[datetime, str], str] | None = latest_by_model_name.get(
                mapping.logical_model_name
            )
            candidate: tuple[tuple[datetime, str], str] = (rank, mapping.physical_name)
            if current is None or candidate > current:
                latest_by_model_name[mapping.logical_model_name] = candidate
    latest_physical_names: frozenset[str] = frozenset(
        value[1] for value in latest_by_model_name.values()
    )
    protected_names: set[str] = set()
    obsolete_removals: list[AdapterStableBindingRemoval] = []
    for binding in managed_table_state.active_bindings:
        if (
            binding.physical_name in known_physical_names
            and binding.physical_name not in latest_physical_names
        ):
            obsolete_removals.append(
                AdapterStableBindingRemoval(
                    database=binding.database,
                    logical_name=binding.logical_name,
                )
            )
            continue
        protected_names.add(binding.physical_name)
    return frozenset(protected_names), tuple(obsolete_removals)
