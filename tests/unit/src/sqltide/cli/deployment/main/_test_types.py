from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentReadCommandTestCase:
    description: str
    expected_exit_code: int
    expected_output_fragment: str
