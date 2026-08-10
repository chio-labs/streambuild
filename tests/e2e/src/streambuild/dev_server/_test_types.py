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
class LineageBrowserE2ETestCase:
    description: str
    route: str
    expected_title: str
    expected_query: str
    expected_source_node_id: str
    expected_model_node_id: str
    expected_node_count: int
    expected_edge_count: int
