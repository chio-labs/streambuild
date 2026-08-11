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
class CliBuildInterruptTestCase:
    description: str
    expected_exit_code: int
    expected_invocation_outcome: str
    expected_stderr_fragment: str
    expected_execution_status: str


@dataclass(frozen=True)
class CliProtectedBuildTestCase:
    description: str
    warning: str
    confirmation: str
    expected_rejected_exit_code: int
    expected_accepted_exit_code: int


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


@dataclass(frozen=True)
class CliMixedBuildTestCase:
    description: str
    expected_exit_code: int
    expected_mode: str
    expected_execution_order: tuple[str, str]
    expected_virtual_phase_fragment: str
    expected_direct_phase_fragment: str
    expected_completion_fragment: str


@dataclass(frozen=True)
class CliRunScopeTestCase:
    description: str
    parent_invocation_id: str
    expected_executed_logical_ids: tuple[tuple[str, ...], ...]
    expected_context_logical_ids: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class CliRejectedPipelineLimitTestCase:
    description: str
    project_max_pipelines: int
    target_max_pipelines: int
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class CliAllowedPipelineLimitTestCase:
    description: str
    project_max_pipelines: int
    selectors: tuple[str, ...]
    expected_exit_code: int
