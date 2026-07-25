from dataclasses import dataclass

from streambuild.compiler.planner.types import RebuildExecutionMode
from streambuild.executor.audit_backfill.types import AuditAssessment


@dataclass(frozen=True)
class GreenfieldKafkaWorkflowE2ETestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_order_ids: tuple[str, ...]
    expected_audit_assessment: AuditAssessment


@dataclass(frozen=True)
class KafkaRecoveryWorkflowE2ETestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_order_ids: tuple[str, ...]
    expected_doctor_state_kind: str


@dataclass(frozen=True)
class KafkaLiveShadowWorkflowE2ETestCase:
    description: str
    deployment_id: str
    initial_order_ids: tuple[str, ...]
    live_order_ids: tuple[str, ...]
    expected_final_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class KafkaOffsetAuditWorkflowE2ETestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    initial_order_ids: tuple[str, ...]
    live_order_ids: tuple[str, ...]
    expected_audit_assessment: AuditAssessment
    expected_partitions_compared: int


@dataclass(frozen=True)
class KafkaSchemaChangeWorkflowE2ETestCase:
    description: str
    initial_pipeline_kind: str
    changed_pipeline_kind: str
    initial_deployment_id: str
    changed_deployment_id: str
    lookback_seconds: int
    expected_execution_mode: RebuildExecutionMode
    expected_view_column_names: tuple[str, ...]
    expected_selected_columns: tuple[str, ...]
    expected_selected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ExternalSourceWorkflowE2ETestCase:
    description: str
    deployment_id: str
    expected_order_ids: tuple[str, ...]
    expected_audit_assessment: AuditAssessment


@dataclass(frozen=True)
class ExternalSourceCursorWorkflowE2ETestCase:
    description: str
    deployment_id: str
    expected_order_ids: tuple[str, ...]
