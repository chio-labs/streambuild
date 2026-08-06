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
