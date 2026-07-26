"""Deployment resolution helpers for publish."""

from streambuild.executor.audit_backfill.models import AuditDeploymentCandidate
from streambuild.executor.publish.exceptions import PublishExecutionError
from streambuild.executor.publish.main.build_publish_deployment_candidates import (
    build_publish_deployment_candidates,
)
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


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
        raise PublishExecutionError("No staged deployment candidates are available for publish")
    candidate_ids: str = ", ".join(candidate.deployment_id for candidate in candidates)
    raise PublishExecutionError(
        f"Publish deployment resolution is ambiguous; choose one of: {candidate_ids}"
    )
