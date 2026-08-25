from dataclasses import dataclass

from streambuild.executor.workflow.types import WorkflowPhase


@dataclass(frozen=True)
class DirectWorkflowTestCase:
    description: str
    expected_first_phase: WorkflowPhase
    expected_last_phase: WorkflowPhase
    expected_replay_count: int
    expected_boundary_model_segments: tuple[str, ...]


@dataclass(frozen=True)
class DirectSourceScopeTestCase:
    description: str
    expected_source_step_ids: tuple[str, ...]
    unexpected_source_step_ids: tuple[str, ...]


@dataclass(frozen=True)
class DirectNoOpWorkflowTestCase:
    description: str
    expected_statement_count: int


@dataclass(frozen=True)
class DirectDistinctCaptureTestCase:
    description: str
    expected_capture_models: tuple[str, ...]
    expected_replay_sql_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DirectCaptureValidationTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class DirectPersistenceFailureTestCase:
    description: str
    selected_model_names: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class DirectFingerprintPersistenceTestCase:
    description: str
    expected_warning_fragment: str


@dataclass(frozen=True)
class DirectFingerprintMetadataTestCase:
    description: str
    model_name: str
    expected_storage_key: str
