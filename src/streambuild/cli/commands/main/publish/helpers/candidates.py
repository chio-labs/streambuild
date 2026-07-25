from __future__ import annotations

from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.executor.audit_backfill.helpers.metadata import load_audit_deployment
from streambuild.executor.audit_backfill.models import (
    AuditDeploymentCandidate,
    LoadedAuditDeployment,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient


def candidate_root_names(inspected_state: InspectedManagedTableState) -> tuple[str, ...]:
    active_root_names: tuple[str, ...] = tuple(
        sorted(
            {
                binding.logical_name
                for binding in inspected_state.active_bindings
                if binding.logical_name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
            }
        )
    )
    if active_root_names:
        return active_root_names

    return tuple(
        sorted(
            {
                candidate.logical_name
                for candidate in inspected_state.physical_candidates
                if candidate.logical_name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
            }
        )
    )


def enrich_candidates(
    *,
    client: ClickHouseClient,
    metadata_database: str,
    candidates: tuple[AuditDeploymentCandidate, ...],
) -> tuple[AuditDeploymentCandidate, ...]:
    enriched_candidates: list[AuditDeploymentCandidate] = []
    candidate: AuditDeploymentCandidate
    for candidate in candidates:
        loaded: LoadedAuditDeployment = load_audit_deployment(
            client,
            metadata_database,
            candidate.deployment_id,
        )
        root_names: tuple[str, ...] = loaded_deployment_root_names(loaded)
        enriched_candidates.append(
            AuditDeploymentCandidate(
                deployment_id=candidate.deployment_id,
                created_at=loaded.created_at,
                deployment_status=loaded.status,
                root_names=root_names,
            )
        )

    return tuple(enriched_candidates)


def loaded_deployment_root_names(loaded: LoadedAuditDeployment) -> tuple[str, ...]:
    root_names: tuple[str, ...] = tuple(
        sorted(
            root_key.name
            for root_key in loaded.root_keys
            if root_key.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
        )
    )
    if root_names:
        return root_names

    return tuple(
        sorted(
            logical_key.name
            for logical_key, _physical_name in loaded.prepared_object_mappings
            if logical_key.object_type == DESIRED_OBJECT_TYPE_TABLE
            and logical_key.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
        )
    )
