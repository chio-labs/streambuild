import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterTargetMutationLockError
from streambuild.adapter.models import AdapterTargetMutationLock
from streambuild.executor.workflow.main.target_mutation_lock import target_mutation_lock
from tests.integration.src.streambuild.adapters.clickhouse._test_types import (
    MissingTargetMutationLockIntegrationTestCase,
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


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        MissingTargetMutationLockIntegrationTestCase(
            description="first build creates its target before acquiring the lock",
            expected_table_count_while_locked=1,
            expected_table_count_after_release=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_target_when_build_locking_then_database_is_created_before_lock(
    test_case: MissingTargetMutationLockIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
    clickhouse_database: str,
) -> None:
    missing_database: str = f"{clickhouse_database}_first_build"
    try:
        with target_mutation_lock(
            connection=managed_clickhouse_client,
            database=missing_database,
            ensure_database=True,
        ):
            locked_count: int = int(
                str(
                    managed_clickhouse_client.query(
                        "SELECT count() FROM system.tables "
                        f"WHERE database = '{missing_database}' "
                        "AND name = '_streambuild_target_mutation_lock'"
                    ).rows[0][0]
                )
            )
        released_count: int = int(
            str(
                managed_clickhouse_client.query(
                    "SELECT count() FROM system.tables "
                    f"WHERE database = '{missing_database}' "
                    "AND name = '_streambuild_target_mutation_lock'"
                ).rows[0][0]
            )
        )

        assert locked_count == test_case.expected_table_count_while_locked
        assert released_count == test_case.expected_table_count_after_release
    finally:
        managed_clickhouse_client.execute_workflow_sql(
            f"DROP DATABASE IF EXISTS {missing_database} SYNC;"
        )
