import pytest

from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import WorkflowExecutionResult
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.workflow._test_types import (
    WorkflowEmitterFailureTestCase,
    WorkflowEmitterTestCase,
    WorkflowQueryIdTestCase,
)
from tests.unit.src.streambuild.executor.workflow.helpers import (
    FailingCompletedWorkflowEmitter,
    FailingMutationConnection,
    FailingStartedWorkflowEmitter,
    QueryIdRecordingConnection,
    RecordingWorkflowEmitter,
    build_test_workflow,
    build_tolerant_failure_workflow,
    build_two_mutation_workflow,
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
        WorkflowQueryIdTestCase(
            description="correlates every statement with the emitter query ID",
            query_id="query-123",
            expected_query_ids=("query-123", "query-123"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_emitter_query_id_when_executing_workflow_then_every_statement_is_correlated(
    test_case: WorkflowQueryIdTestCase,
) -> None:
    emitter: RecordingWorkflowEmitter = RecordingWorkflowEmitter(query_id=test_case.query_id)
    connection: QueryIdRecordingConnection = QueryIdRecordingConnection()

    execute_warehouse_workflow(
        statements=build_test_workflow(plan_json='{"mode":"direct"}\n').statements,
        connection=connection,
        emitter=emitter,
    )

    assert tuple(connection.query_ids) == test_case.expected_query_ids


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


@pytest.mark.parametrize(
    "test_case",
    [
        WorkflowEmitterFailureTestCase(
            description="started event failure prevents the next mutation",
            failed_step_id="mutation_two",
            expected_partial_step_ids=("mutation_one",),
            expected_dispatched_statements=("INSERT INTO events VALUES (1);",),
            expected_error_fragment="statement started persistence failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_started_emitter_failure_when_executing_then_statement_is_not_dispatched(
    test_case: WorkflowEmitterFailureTestCase,
) -> None:
    emitter: FailingStartedWorkflowEmitter = FailingStartedWorkflowEmitter(
        failed_step_id=test_case.failed_step_id
    )
    connection: RecordingAdapterConnection = RecordingAdapterConnection()

    with pytest.raises(WorkflowExecutionError) as captured:
        execute_warehouse_workflow(
            statements=build_two_mutation_workflow().statements,
            connection=connection,
            emitter=emitter,
        )

    assert isinstance(captured.value.partial_result, WorkflowExecutionResult)
    partial: WorkflowExecutionResult = captured.value.partial_result
    assert tuple(result.step_id for result in partial.statement_results) == (
        test_case.expected_partial_step_ids
    )
    assert tuple(connection.statements) == test_case.expected_dispatched_statements
    assert test_case.expected_error_fragment in str(captured.value.cause)


@pytest.mark.parametrize(
    "test_case",
    [
        WorkflowEmitterFailureTestCase(
            description="completed event failure retains the successful mutation prefix",
            failed_step_id="mutation_one",
            expected_partial_step_ids=("mutation_one",),
            expected_dispatched_statements=("INSERT INTO events VALUES (1);",),
            expected_error_fragment="statement completed persistence failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_successful_mutation_when_completion_emitter_fails_then_partial_includes_mutation(
    test_case: WorkflowEmitterFailureTestCase,
) -> None:
    emitter: FailingCompletedWorkflowEmitter = FailingCompletedWorkflowEmitter(
        failed_step_id=test_case.failed_step_id
    )
    connection: RecordingAdapterConnection = RecordingAdapterConnection()

    with pytest.raises(WorkflowExecutionError) as captured:
        execute_warehouse_workflow(
            statements=build_two_mutation_workflow().statements,
            connection=connection,
            emitter=emitter,
        )

    assert isinstance(captured.value.partial_result, WorkflowExecutionResult)
    partial: WorkflowExecutionResult = captured.value.partial_result
    assert tuple(result.step_id for result in partial.statement_results) == (
        test_case.expected_partial_step_ids
    )
    assert partial.statement_results[0].mutation_result is not None
    assert tuple(connection.statements) == test_case.expected_dispatched_statements
    assert test_case.expected_error_fragment in str(captured.value.cause)
