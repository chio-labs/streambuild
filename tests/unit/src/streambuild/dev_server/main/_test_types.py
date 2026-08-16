from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledBatchFailureTestCase:
    description: str
    error_message: str
    scheduled_for: str
    expected_status: str
    expected_result_count: int


@dataclass(frozen=True)
class AuthBindTestCase:
    description: str
    expected_result: object
