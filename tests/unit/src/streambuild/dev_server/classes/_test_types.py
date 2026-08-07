from dataclasses import dataclass


@dataclass(frozen=True)
class BuildCancellationStateTestCase:
    description: str
    invocation_id: str
    expected_cancel_status: str
    expected_force_available: bool
