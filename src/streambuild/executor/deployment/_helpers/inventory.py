"""Authoritative deployment inventory reconstruction."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import VIRTUAL_DEPLOYMENT_STATUS_INCOMPLETE
from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterPublishEventRecord,
    CatalogSnapshot,
    InspectedActiveTableBinding,
    InspectedManagedTableState,
    InspectedPhysicalTableCandidate,
)
from streambuild.compiler.planner.main.deployment_id_from_physical_name import (
    deployment_id_from_physical_name,
)
from streambuild.compiler.planner.main.is_deployment_physical_name import (
    is_deployment_physical_name,
)
from streambuild.executor.deployment.models import DeploymentInventory, DeploymentSummary
from streambuild.executor.deployment.types import DeploymentLifecycleState


def build_deployment_inventory(
    *, client: AdapterConnection, metadata_database: str, default_database: str
) -> DeploymentInventory:
    """Combine append-only lifecycle records with current warehouse evidence."""
    persisted: AdapterDeploymentInventory = client.load_deployment_inventory(metadata_database)
    inspected: InspectedManagedTableState = client.inspect_managed_table_state(default_database)
    catalog: CatalogSnapshot = client.load_catalog(default_database)
    records_by_id: dict[str, AdapterDeploymentRecord] = {
        record.deployment_id: record for record in persisted.deployments
    }
    physical_by_id: dict[str, set[str]] = _physical_relations_by_deployment(inspected)
    active_by_id: dict[str, set[str]] = _active_bindings_by_deployment(inspected)
    publications_by_id: dict[str, tuple[AdapterPublishEventRecord, ...]] = (
        _publications_by_deployment(persisted.publish_events)
    )
    deployment_ids: set[str] = (
        set(records_by_id) | set(physical_by_id) | set(active_by_id) | set(publications_by_id)
    )
    existing_names: frozenset[str] = catalog.relation_names()
    summaries: tuple[DeploymentSummary, ...] = tuple(
        _build_summary(
            deployment_id=deployment_id,
            record=records_by_id.get(deployment_id),
            discovered_physical_names=physical_by_id.get(deployment_id, set()),
            active_binding_names=active_by_id.get(deployment_id, set()),
            publications=publications_by_id.get(deployment_id, ()),
            existing_names=existing_names,
        )
        for deployment_id in sorted(deployment_ids, reverse=True)
    )
    return DeploymentInventory(database=default_database, deployments=summaries)


def _physical_relations_by_deployment(
    inspected: InspectedManagedTableState,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    candidate: InspectedPhysicalTableCandidate
    for candidate in inspected.physical_candidates:
        if is_deployment_physical_name(candidate.physical_name):
            deployment_id: str = deployment_id_from_physical_name(candidate.physical_name)
            result.setdefault(deployment_id, set()).add(candidate.physical_name)
    return result


def _active_bindings_by_deployment(
    inspected: InspectedManagedTableState,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    binding: InspectedActiveTableBinding
    for binding in inspected.active_bindings:
        if is_deployment_physical_name(binding.physical_name):
            deployment_id: str = deployment_id_from_physical_name(binding.physical_name)
            result.setdefault(deployment_id, set()).add(binding.logical_name)
    return result


def _publications_by_deployment(
    events: tuple[AdapterPublishEventRecord, ...],
) -> dict[str, tuple[AdapterPublishEventRecord, ...]]:
    result: dict[str, tuple[AdapterPublishEventRecord, ...]] = {}
    deployment_id: str
    for deployment_id in sorted({event.deployment_id for event in events}):
        result[deployment_id] = tuple(
            event for event in events if event.deployment_id == deployment_id
        )
    return result


def _build_summary(
    *,
    deployment_id: str,
    record: AdapterDeploymentRecord | None,
    discovered_physical_names: set[str],
    active_binding_names: set[str],
    publications: tuple[AdapterPublishEventRecord, ...],
    existing_names: frozenset[str],
) -> DeploymentSummary:
    mapped_names: set[str] = (
        set()
        if record is None
        else {mapping.physical_name for mapping in record.prepared_object_mappings}
    )
    physical_names: tuple[str, ...] = tuple(sorted(mapped_names | discovered_physical_names))
    missing_names: tuple[str, ...] = tuple(sorted(mapped_names - existing_names))
    return DeploymentSummary(
        deployment_id=deployment_id,
        state=_lifecycle_state(
            record=record,
            active_binding_names=active_binding_names,
            publications=publications,
            mapped_names=mapped_names,
            missing_names=missing_names,
        ),
        created_at=None if record is None else record.created_at,
        persisted_status=None if record is None else record.status,
        root_names=_root_names(record),
        physical_relation_names=physical_names,
        missing_physical_relation_names=missing_names,
        active_binding_names=tuple(sorted(active_binding_names)),
        latest_published_at=max((event.published_at for event in publications), default=None),
    )


def _lifecycle_state(
    *,
    record: AdapterDeploymentRecord | None,
    active_binding_names: set[str],
    publications: tuple[AdapterPublishEventRecord, ...],
    mapped_names: set[str],
    missing_names: tuple[str, ...],
) -> DeploymentLifecycleState:
    if record is None:
        return DeploymentLifecycleState.METADATA_MISSING
    if record.status == VIRTUAL_DEPLOYMENT_STATUS_INCOMPLETE:
        return DeploymentLifecycleState.INCOMPLETE
    if missing_names:
        return DeploymentLifecycleState.PHYSICAL_MISSING
    if active_binding_names:
        return DeploymentLifecycleState.ACTIVE
    if publications:
        return DeploymentLifecycleState.SUPERSEDED
    if not mapped_names:
        return DeploymentLifecycleState.PHYSICAL_MISSING
    return DeploymentLifecycleState.STAGED


def _root_names(record: AdapterDeploymentRecord | None) -> tuple[str, ...]:
    if record is None:
        return ()
    selected: tuple[str, ...] = tuple(sorted({key.name for key in record.selected_root_keys}))
    if selected:
        return selected
    return tuple(sorted({mapping.logical_key.name for mapping in record.prepared_object_mappings}))
