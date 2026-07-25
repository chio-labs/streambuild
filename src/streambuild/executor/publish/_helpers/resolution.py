"""Deployment resolution helpers for publish."""

from streambuild.clickhouse.inspect._helpers.deployments import inspect_root_deployment_state
from streambuild.clickhouse.inspect.main import inspect_managed_table_state
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.compiler.shared._helpers.deployment_names import deployment_id_from_physical_name
from streambuild.compiler.shared.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.shared.models import ObjectKey
from streambuild.executor.audit_backfill.models import AuditDeploymentCandidate
from streambuild.integrations.clickhouse.client import ClickHouseClient


def resolve_publish_deployment_id(
    *,
    client: ClickHouseClient,
    metadata_database: str,
    default_database: str,
    deployment_id: str | None,
) -> str:
    """Resolve the deployment id to publish, requiring explicit choice when ambiguous."""

    if deployment_id is not None:
        return deployment_id

    candidates: tuple[AuditDeploymentCandidate, ...] = build_publish_deployment_candidates(
        client=client,
        metadata_database=metadata_database,
        default_database=default_database,
    )
    if len(candidates) == 1:
        return candidates[0].deployment_id
    if not candidates:
        raise ValueError("No staged deployment candidates are available for publish")
    candidate_ids: str = ", ".join(candidate.deployment_id for candidate in candidates)
    raise ValueError(f"Publish deployment resolution is ambiguous; choose one of: {candidate_ids}")


def build_publish_deployment_candidates(
    *,
    client: ClickHouseClient,
    metadata_database: str,
    default_database: str,
) -> tuple[AuditDeploymentCandidate, ...]:
    """Build candidate staged deployments visible to publish default resolution."""

    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=default_database,
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

    active_deployment_ids: set[str] = {
        inspection.active_deployment_id
        for inspection in (
            inspect_root_deployment_state(inspected_state=inspected_state, root_key=root_key)
            for root_key in relevant_root_keys
        )
        if inspection.active_deployment_id is not None
    }
    if len(active_deployment_ids) != 1:
        return tuple(AuditDeploymentCandidate(deployment_id=value) for value in all_deployment_ids)

    active_deployment_id: str = next(iter(active_deployment_ids))
    return tuple(
        AuditDeploymentCandidate(deployment_id=value)
        for value in all_deployment_ids
        if value > active_deployment_id
    )
