import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterTargetMutationLockError
from streambuild.adapter.models import AdapterTargetMutationLock
from tests.integration.src.streambuild.adapters.clickhouse._test_types import (
    TargetMutationLockIntegrationTestCase,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockIntegrationTestCase(
            description="competing owner waits for lock release",
            initial_owner_id="first-run",
            competing_owner_id="second-run",
            expected_initial_owner_id="first-run",
            expected_reacquired_owner_id="second-run",
            expected_error_message="already mutation-locked by 'first-run'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_real_clickhouse_when_locking_target_then_only_one_owner_can_mutate(
    test_case: TargetMutationLockIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
    clickhouse_database: str,
) -> None:
    first: AdapterTargetMutationLock = managed_clickhouse_client.acquire_target_mutation_lock(
        database=clickhouse_database,
        owner_id=test_case.initial_owner_id,
    )
    try:
        assert first.owner_id == test_case.expected_initial_owner_id
        with pytest.raises(
            AdapterTargetMutationLockError,
            match=test_case.expected_error_message,
        ):
            managed_clickhouse_client.acquire_target_mutation_lock(
                database=clickhouse_database,
                owner_id=test_case.competing_owner_id,
            )
    finally:
        managed_clickhouse_client.release_target_mutation_lock(first)

    second: AdapterTargetMutationLock = managed_clickhouse_client.acquire_target_mutation_lock(
        database=clickhouse_database,
        owner_id=test_case.competing_owner_id,
    )
    try:
        assert second.owner_id == test_case.expected_reacquired_owner_id
    finally:
        managed_clickhouse_client.release_target_mutation_lock(second)
