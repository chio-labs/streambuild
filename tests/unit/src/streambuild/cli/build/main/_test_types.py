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
    expected_invocation_outcome: str


@dataclass(frozen=True)
class CliBuildArtifactTestCase:
    description: str
    expected_exit_code: int
    expected_mode: str
    expected_adapter: str
    expected_artifact_path: str


@dataclass(frozen=True)
class CliVirtualBuildArtifactTestCase:
    description: str
    deployment_id: str
    expected_created_at: str
    expected_mode: str
    expected_exit_code: int
