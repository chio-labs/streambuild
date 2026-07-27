"""Build the selectable audit deployment candidates for a target."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import InspectedManagedTableState
from streambuild.compiler.compile.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.planner.main.deployment_id_from_physical_name import (
    deployment_id_from_physical_name,
)
from streambuild.compiler.planner.main.inspect_root_deployment_state import (
    inspect_root_deployment_state,
)
from streambuild.executor.audit_backfill.models import AuditDeploymentCandidate


def build_audit_deployment_candidates(
    *,
    client: AdapterConnection,
    metadata_database: str,
    default_database: str,
) -> tuple[AuditDeploymentCandidate, ...]:
    """Build candidate staged deployments visible to audit default resolution."""

    inspected_state: InspectedManagedTableState = client.inspect_managed_table_state(
        default_database
    )
    all_deployment_ids: tuple[str, ...] = tuple(
        sorted(
            {
                deployment_id_from_physical_name(candidate.physical_name)
                for candidate in inspected_state.physical_candidates
            }
        )
    )
    relevant_root_keys: tuple[ObjectKey, ...] = tuple(
        ObjectKey(
            database=default_database,
            object_type=DESIRED_OBJECT_TYPE_TABLE,
            name=binding.logical_name,
        )
        for binding in inspected_state.active_bindings
    )
    if not relevant_root_keys:
        return tuple(AuditDeploymentCandidate(deployment_id=value) for value in all_deployment_ids)

    active_deployment_ids: set[str] = set()
    root_key: ObjectKey
    for root_key in relevant_root_keys:
        active_deployment_id: str | None = inspect_root_deployment_state(
            inspected_state=inspected_state, root_key=root_key
        ).active_deployment_id
        if active_deployment_id is not None:
            active_deployment_ids.add(active_deployment_id)
    if len(active_deployment_ids) != 1:
        return tuple(AuditDeploymentCandidate(deployment_id=value) for value in all_deployment_ids)

    active_deployment_id: str = next(iter(active_deployment_ids))
    return tuple(
        AuditDeploymentCandidate(deployment_id=value)
        for value in all_deployment_ids
        if value > active_deployment_id
    )
