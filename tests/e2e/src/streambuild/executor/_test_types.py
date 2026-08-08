from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.types import RebuildExecutionMode
from streambuild.executor.readiness.types import AuditAssessment


@dataclass(frozen=True)
class GreenfieldKafkaWorkflowE2ETestCase:
    description: str
    fixture_project_dir: Path
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_order_ids: tuple[str, ...]
    expected_audit_assessment: AuditAssessment
    expected_replay_lineage_mode: ReplayLineageMode
    produced_headers: tuple[tuple[str, bytes], ...]
    expected_header_keys: tuple[str, ...]
    expected_header_values: tuple[str, ...]


@dataclass(frozen=True)
class ManagedSourceBootstrapE2ETestCase:
    description: str
    fixture_project_dir: Path
    deployment_id: str
    expected_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class DirectManagedManualWorkflowE2ETestCase:
    description: str
    messages: tuple[tuple[str, str], ...]
    expected_order_ids: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class VirtualManagedManualWorkflowE2ETestCase:
    description: str
    deployment_ids: tuple[str, str, str]
    messages: tuple[tuple[str, str], ...]
    expected_order_ids: tuple[str, ...]
    expected_watermark_rows: tuple[tuple[str, str], ...]
    expected_audit_assessment: AuditAssessment
    expected_deployment_status: str
    expected_publish_event_count: int
    expected_stable_bindings: tuple[tuple[str, str], ...]
    expected_exit_code: int
    expected_min_physical_relation_count: int


class VirtualManagedManualWorkflowSnapshot(NamedTuple):
    deployment_status: str
    deployment_metadata: tuple[tuple[str, ...], ...]
    physical_graph: tuple[tuple[str, ...], ...]
    replay_order_ids: tuple[str, ...]
    watermark_rows: tuple[tuple[str, str], ...]
    audit_assessment: str
    publish_event_count: int
    stable_bindings: tuple[tuple[str, str], ...]


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


class KafkaLiveShadowScenarioResult(NamedTuple):
    staged_table_name: str
    staged_order_ids: tuple[str, ...]
    deployment_id: str
    final_rows: tuple[tuple[object, ...], ...]


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
    topic_row_indexes: tuple[int, ...] = ()


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


@dataclass(frozen=True)
class ExternalSourceOffsetWorkflowE2ETestCase:
    description: str
    deployment_id: str
    expected_order_ids: tuple[str, ...]
    expected_watermark_rows: tuple[tuple[str, str], ...]
    expected_replay_lineage_mode: ReplayLineageMode


@dataclass(frozen=True)
class DirectExternalSourceBuildE2ETestCase:
    description: str
    expected_order_ids: tuple[str, ...]
