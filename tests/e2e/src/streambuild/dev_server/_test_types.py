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
