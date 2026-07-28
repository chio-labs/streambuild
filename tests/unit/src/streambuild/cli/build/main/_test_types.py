from dataclasses import dataclass


@dataclass(frozen=True)
class CliBuildGateTestCase:
    description: str
    virtual_environments: bool | None
    json_output: bool
    auto_approve: bool
    confirmation_response: str
    expected_exit_code: int
    expected_stderr_fragment: str
    expected_stdout_fragment: str
