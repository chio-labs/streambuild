"""Audit backfill execution entrypoint."""

from streambuild.clickhouse.inspect.main import inspect_managed_table_state
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.executor.audit_backfill._helpers.comparisons import build_root_audit_results
from streambuild.executor.audit_backfill._helpers.metadata import load_audit_deployment
from streambuild.executor.audit_backfill._helpers.resolution import resolve_audit_deployment_id
from streambuild.executor.audit_backfill.models import (
    AuditBackfillRequest,
    AuditBackfillResult,
    LoadedAuditDeployment,
    RootAuditResult,
)
from streambuild.executor.audit_backfill.types import AuditAssessment
from streambuild.integrations.clickhouse.client import ClickHouseClient


def execute_audit_backfill(
    *,
    request: AuditBackfillRequest,
    client: ClickHouseClient,
) -> AuditBackfillResult:
    """Audit a staged backfill deployment by explicit deployment id."""

    resolved_deployment_id: str = resolve_audit_deployment_id(
        client=client,
        metadata_database=request.metadata_database,
        default_database=request.default_database,
        deployment_id=request.deployment_id,
    )
    loaded_deployment: LoadedAuditDeployment = load_audit_deployment(
        client=client,
        metadata_database=request.metadata_database,
        deployment_id=resolved_deployment_id,
    )
    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=request.default_database,
    )
    root_results: tuple[RootAuditResult, ...] = build_root_audit_results(
        client=client,
        default_database=request.default_database,
        deployment_id=resolved_deployment_id,
        inspected_state=inspected_state,
    )
    if not root_results:
        raise ValueError(
            f"Deployment '{resolved_deployment_id}' has no staged physical tables to audit"
        )
    return AuditBackfillResult(
        deployment_id=resolved_deployment_id,
        deployment_status=loaded_deployment.status,
        assessment=_build_overall_assessment(root_results),
        replay_lineage_mode=loaded_deployment.replay_lineage_mode,
        warning_codes=loaded_deployment.warning_codes,
        root_results=root_results,
    )


def _build_overall_assessment(root_results: tuple[RootAuditResult, ...]) -> AuditAssessment:
    if any(root_result.assessment == AuditAssessment.NOT_READY for root_result in root_results):
        return AuditAssessment(AuditAssessment.NOT_READY)
    if any(root_result.assessment == AuditAssessment.CAUTION for root_result in root_results):
        return AuditAssessment(AuditAssessment.CAUTION)
    return AuditAssessment(AuditAssessment.READY)
