from dataclasses import dataclass

from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.executor.audit_backfill.types import AuditAssessment


@dataclass(frozen=True)
class ExecuteAuditBackfillIntegrationTestCase:
    description: str
    replay_lineage_mode: ReplayLineageMode | str
    deployment_id: str
    active_deployment_id: str
    created_at: str
    boundary_time: str
    staged_includes_live_row: bool
    historical_row_time: str
    live_row_time: str
    expected_assessment: AuditAssessment
    expected_root_name: str
    expected_staged_physical_name: str
    expected_active_exists: bool
    expected_active_row_count: int | None
    expected_staged_row_count: int | None
    expected_warning_codes: tuple[str, ...]
    expected_root_warnings: tuple[str, ...] = ()
    staged_is_empty: bool = False
    extra_active_only_rows: int = 0
    expected_catchup_kind: str = "scalar"
    expected_partitions_compared: int | None = None


@dataclass(frozen=True)
class ResolveAuditDeploymentIntegrationTestCase:
    description: str
    create_active_view: bool
    first_deployment_id: str
    second_deployment_id: str
    expected_resolved_deployment_id: str | None
    expected_error_fragment: str | None


@dataclass(frozen=True)
class AuditWithoutMetadataIntegrationTestCase:
    description: str
    deployment_id: str
    expected_assessment: AuditAssessment
    expected_active_exists: bool


@dataclass(frozen=True)
class DanglingActiveViewAuditIntegrationTestCase:
    description: str
    deployment_id: str
    active_deployment_id: str
    expected_assessment: AuditAssessment


@dataclass(frozen=True)
class AuditAfterDeletedActiveViewIntegrationTestCase:
    description: str
    deployment_id: str
    active_deployment_id: str
    expected_assessment: AuditAssessment


@dataclass(frozen=True)
class OffsetAuditDegradedStateIntegrationTestCase:
    description: str
    deployment_id: str
    active_deployment_id: str
    scenario_kind: str
    expected_assessment: AuditAssessment
