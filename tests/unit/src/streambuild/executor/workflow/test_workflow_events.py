import pytest

from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import WorkflowExecutionResult
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.workflow._test_types import WorkflowEmitterTestCase
from tests.unit.src.streambuild.executor.workflow.helpers import (
    FailingMutationConnection,
    RecordingWorkflowEmitter,
    build_test_workflow,
    build_tolerant_failure_workflow,
)


@pytest.mark.parametrize(
    "test_case",
    [
        WorkflowEmitterTestCase(
            description="emits a started and completed pair per statement in order",
            expected_calls=(
                "started:check_ready",
                "completed:check_ready:None",
                "started:insert_event",
                "completed:insert_event:None",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_emitter_when_executing_workflow_then_narrates_every_statement(
    test_case: WorkflowEmitterTestCase,
) -> None:
    emitter: RecordingWorkflowEmitter = RecordingWorkflowEmitter()
    connection: RecordingAdapterConnection = RecordingAdapterConnection()

    result: WorkflowExecutionResult = execute_warehouse_workflow(
        statements=build_test_workflow(plan_json='{"mode":"direct"}\n').statements,
        connection=connection,
        emitter=emitter,
    )

    assert tuple(emitter.calls) == test_case.expected_calls
    assert len(result.statement_results) == 2


@pytest.mark.parametrize(
    "test_case",
    [
        WorkflowEmitterTestCase(
            description="a tolerated failure is narrated with its error message",
            expected_calls=(
                "started:check_ready",
                "completed:check_ready:None",
                "started:insert_event",
                "completed:insert_event:mutation rejected: INSERT INTO events VALUES (1);",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_tolerated_failure_when_executing_then_completion_carries_the_error(
    test_case: WorkflowEmitterTestCase,
) -> None:
    emitter: RecordingWorkflowEmitter = RecordingWorkflowEmitter()
    connection: FailingMutationConnection = FailingMutationConnection()

    result: WorkflowExecutionResult = execute_warehouse_workflow(
        statements=build_tolerant_failure_workflow().statements,
        connection=connection,
        emitter=emitter,
    )

    assert tuple(emitter.calls) == test_case.expected_calls
    assert result.statement_results[1].error_message is not None
