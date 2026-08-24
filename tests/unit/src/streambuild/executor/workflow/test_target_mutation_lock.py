from uuid import UUID

import pytest

from streambuild.adapter.exceptions import AdapterTargetMutationLockError
from streambuild.adapter.models import AdapterTargetMutationLock
from streambuild.executor.workflow.main.target_mutation_lock import target_mutation_lock
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.workflow._test_types import (
    TargetMutationLockTestCase,
)


class ContendedMutationConnection(RecordingAdapterConnection):
    def acquire_target_mutation_lock(
        self, *, database: str, owner_id: str
    ) -> AdapterTargetMutationLock:
        self.target_mutation_lock_events.append(("acquire", database, owner_id))
        self.operation_events.append(f"acquire:{database}")
        raise AdapterTargetMutationLockError("target mutation lock is already held")


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockTestCase(
            description="successful mutation is enclosed by exact target lock",
            database="analytics-uat",
            expected_events=("acquire:analytics-uat", "mutation", "release:analytics-uat"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_available_target_when_mutating_then_lock_encloses_operation(
    test_case: TargetMutationLockTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection()

    with target_mutation_lock(connection=connection, database=test_case.database):
        connection.execute_workflow_sql("DROP TABLE analytics.orders;")

    acquired: tuple[str, str, str] = connection.target_mutation_lock_events[0]
    released: tuple[str, str, str] = connection.target_mutation_lock_events[1]
    assert connection.operation_events == list(test_case.expected_events)
    assert UUID(acquired[2]).version == 4
    assert released == ("release", test_case.database, acquired[2])


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockTestCase(
            description="operation error still releases exact target lock",
            database="analytics",
            expected_events=("acquire:analytics", "mutation", "release:analytics"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_operation_error_when_mutating_then_lock_is_released(
    test_case: TargetMutationLockTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection()

    with pytest.raises(RuntimeError, match="mutation failed"):
        with target_mutation_lock(connection=connection, database=test_case.database):
            connection.execute_workflow_sql("DROP TABLE analytics.orders;")
            raise RuntimeError("mutation failed")

    assert connection.operation_events == list(test_case.expected_events)
    assert (
        connection.target_mutation_lock_events[1][2]
        == (connection.target_mutation_lock_events[0][2])
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockTestCase(
            description="contended target prevents operation body mutation",
            database="analytics",
            expected_events=("acquire:analytics",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_contended_target_when_mutating_then_operation_does_not_start(
    test_case: TargetMutationLockTestCase,
) -> None:
    connection: ContendedMutationConnection = ContendedMutationConnection()

    with pytest.raises(AdapterTargetMutationLockError, match="already held"):
        with target_mutation_lock(connection=connection, database=test_case.database):
            connection.execute_workflow_sql("DROP TABLE analytics.orders;")

    assert connection.operation_events == list(test_case.expected_events)
