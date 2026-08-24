from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowPublicationTestCase:
    description: str
    expected_plan_json: str
    expected_workflow_sql: str
    expected_step_filenames: tuple[str, ...]
    expected_workflow_sha256: str


@dataclass(frozen=True)
class WorkflowExecutionTestCase:
    description: str
    expected_statements: tuple[str, ...]
    expected_query_result_count: int
    expected_mutation_result_count: int


@dataclass(frozen=True)
class WorkflowEmitterTestCase:
    description: str
    expected_calls: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowQueryIdTestCase:
    description: str
    query_id: str
    expected_query_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowEmitterFailureTestCase:
    description: str
    failed_step_id: str
    expected_partial_step_ids: tuple[str, ...]
    expected_dispatched_statements: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class WorkflowPersistenceFailureTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class TargetMutationLockTestCase:
    description: str
    database: str
    expected_events: tuple[str, ...]
