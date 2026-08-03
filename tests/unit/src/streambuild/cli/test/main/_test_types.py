from dataclasses import dataclass


@dataclass(frozen=True)
class FailedTestInvocationTestCase:
    description: str
    expected_command: str
    expected_outcome: str
    expected_error_fragment: str
