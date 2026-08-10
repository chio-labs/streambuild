from dataclasses import dataclass


@dataclass(frozen=True)
class SchedulerProcessE2ETestCase:
    description: str
    expected_scheduler_state: str
    expected_result_status: str
    expected_run_mode: str


@dataclass(frozen=True)
class MessageBrowserProcessE2ETestCase:
    description: str
    produced_messages: tuple[tuple[str, str, tuple[tuple[str, bytes], ...]], ...]
    filtered_order_id: str
    expected_filtered_key: str
    expected_filtered_headers: tuple[tuple[str, str], ...]
    expected_facet_values: tuple[str, ...]


@dataclass(frozen=True)
class LineageExactActivityE2ETestCase:
    description: str
    expected_title: str
    expected_logical_counts: str
    expected_physical_counts: str
    expected_multi_command: str
    expected_model_only_command: str
    expected_moving_state: str
    expected_idle_state: str
    expected_stalled_state: str
    expected_source: str


@dataclass(frozen=True)
class LineageApproximateActivityE2ETestCase:
    description: str
    expected_counts: str
    expected_moving_state: str
    expected_unknown_state: str
    expected_moving_source: str
    expected_unknown_source: str


@dataclass(frozen=True)
class PlanBrowserE2ETestCase:
    description: str
    selector: str
    expected_command_suffix: str
    expected_replay_rows: int


@dataclass(frozen=True)
class BuildRunBrowserE2ETestCase:
    description: str
    selector: str
    expected_start_status: str
    expected_outcome: str
    expected_model_node_id: str


@dataclass(frozen=True)
class SourceTopicBrowserE2ETestCase:
    description: str
    source_name: str
    expected_kind: str
    expected_retained_rows: int


@dataclass(frozen=True)
class MessageConsoleBrowserE2ETestCase:
    description: str
    source_name: str
    filtered_order_id: str
    expected_header_name: str
    expected_header_value: str


@dataclass(frozen=True)
class CatalogPipelineBrowserE2ETestCase:
    description: str
    pipeline_name: str
    parent_model: str
    child_model: str
    expected_relation: str
    expected_child_relation: str


@dataclass(frozen=True)
class DeploymentBrowserE2ETestCase:
    description: str
    expected_changed_model: str
    expected_active_value: str
    expected_staged_value: str
    missing_deployment_id: str


@dataclass(frozen=True)
class QualityBrowserE2ETestCase:
    description: str
    expected_passing: int
    expected_warning: int
    expected_failing: int
    expected_sample_key: str
