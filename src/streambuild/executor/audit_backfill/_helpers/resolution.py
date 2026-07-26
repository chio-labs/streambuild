"""Deployment resolution helpers for audit backfill."""

from streambuild.executor.audit_backfill.exceptions import AuditBackfillExecutionError
from streambuild.executor.audit_backfill.main.build_audit_deployment_candidates import (
    build_audit_deployment_candidates,
)
from streambuild.executor.audit_backfill.models import AuditDeploymentCandidate
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def resolve_audit_deployment_id(
    *,
    client: ClickHouseClient,
    metadata_database: str,
    default_database: str,
    deployment_id: str | None,
) -> str:
    """Resolve the deployment id to audit, requiring explicit choice when ambiguous."""

    if deployment_id is not None:
        return deployment_id

    candidates: tuple[AuditDeploymentCandidate, ...] = build_audit_deployment_candidates(
        client=client,
        metadata_database=metadata_database,
        default_database=default_database,
    )
    if len(candidates) == 1:
        return candidates[0].deployment_id
    if not candidates:
        raise AuditBackfillExecutionError("No staged deployment candidates are available for audit")
    candidate_ids: str = ", ".join(candidate.deployment_id for candidate in candidates)
    raise AuditBackfillExecutionError(
        f"Audit deployment resolution is ambiguous; choose one of: {candidate_ids}"
    )
