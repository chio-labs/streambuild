from dataclasses import dataclass


@dataclass(frozen=True)
class SchedulerProcessE2ETestCase:
    description: str
    expected_scheduler_state: str
    expected_result_status: str
    expected_run_mode: str
