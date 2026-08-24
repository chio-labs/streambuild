import pytest

from streambuild.adapter.exceptions import (
    AdapterTargetMutationLockError,
    AdapterWarehouseError,
)
from streambuild.adapter.models import AdapterTargetMutationLock
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    TargetMutationLockAcquireTestCase,
    TargetMutationLockConflictTestCase,
    TargetMutationLockOwnershipChangeTestCase,
    TargetMutationLockReleaseTestCase,
)
from tests.unit.src.streambuild.adapters.clickhouse.helpers import (
    ConflictingTargetMutationLockConnection,
    RecordingTargetMutationLockConnection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockAcquireTestCase(
            description="quoted database and owner",
            database="analytics-uat",
            owner_id="run'123",
            expected_lock=AdapterTargetMutationLock(
                database="analytics-uat",
                owner_id="run'123",
            ),
            expected_statements=(
                "CREATE TABLE `analytics-uat`.`_streambuild_target_mutation_lock` "
                "(guard UInt8) ENGINE = TinyLog COMMENT "
                "'streambuild-target-lock-v2:run''123';",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unlocked_target_when_acquiring_then_atomically_records_owner(
    test_case: TargetMutationLockAcquireTestCase,
) -> None:
    connection: RecordingTargetMutationLockConnection = RecordingTargetMutationLockConnection()

    lock: AdapterTargetMutationLock = connection.acquire_target_mutation_lock(
        database=test_case.database,
        owner_id=test_case.owner_id,
    )

    assert lock == test_case.expected_lock
    assert tuple(connection.statements) == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockConflictTestCase(
            description="target already owned by active run",
            database="analytics",
            current_owner_id="active-run",
            requested_owner_id="new-run",
            expected_error_message="already mutation-locked by 'active-run'",
            expected_statements=(
                "CREATE TABLE `analytics`.`_streambuild_target_mutation_lock` "
                "(guard UInt8) ENGINE = TinyLog COMMENT 'streambuild-target-lock-v2:new-run';",
                "SELECT comment FROM system.tables WHERE database = 'analytics' "
                "AND name = '_streambuild_target_mutation_lock' LIMIT 1",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_locked_target_when_acquiring_then_reports_current_owner(
    test_case: TargetMutationLockConflictTestCase,
) -> None:
    connection: ConflictingTargetMutationLockConnection = ConflictingTargetMutationLockConnection(
        owner_rows=((f"streambuild-target-lock-v2:{test_case.current_owner_id}",),),
    )

    with pytest.raises(
        AdapterTargetMutationLockError,
        match=test_case.expected_error_message,
    ):
        connection.acquire_target_mutation_lock(
            database=test_case.database,
            owner_id=test_case.requested_owner_id,
        )

    assert tuple(connection.statements) == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockConflictTestCase(
            description="create failure without lock metadata remains a warehouse error",
            database="analytics",
            current_owner_id="",
            requested_owner_id="new-run",
            expected_error_message="table already exists",
            expected_statements=(
                "CREATE TABLE `analytics`.`_streambuild_target_mutation_lock` "
                "(guard UInt8) ENGINE = TinyLog COMMENT 'streambuild-target-lock-v2:new-run';",
                "SELECT comment FROM system.tables WHERE database = 'analytics' "
                "AND name = '_streambuild_target_mutation_lock' LIMIT 1",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unrelated_create_failure_when_acquiring_then_original_error_is_preserved(
    test_case: TargetMutationLockConflictTestCase,
) -> None:
    connection: ConflictingTargetMutationLockConnection = ConflictingTargetMutationLockConnection()

    with pytest.raises(AdapterWarehouseError, match=test_case.expected_error_message):
        connection.acquire_target_mutation_lock(
            database=test_case.database,
            owner_id=test_case.requested_owner_id,
        )

    assert tuple(connection.statements) == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockReleaseTestCase(
            description="lock still owned by releasing run",
            lock=AdapterTargetMutationLock(database="analytics", owner_id="run-123"),
            expected_statements=(
                "CREATE TABLE `analytics`."
                "`_streambuild_target_mutation_lock_release_272812a7ae467f0d` "
                "(guard UInt8) ENGINE = TinyLog COMMENT 'streambuild-target-lock-v2:run-123';",
                "EXCHANGE TABLES `analytics`.`_streambuild_target_mutation_lock` AND "
                "`analytics`.`_streambuild_target_mutation_lock_release_272812a7ae467f0d`;",
                "SELECT comment FROM system.tables WHERE database = 'analytics' AND name = "
                "'_streambuild_target_mutation_lock_release_272812a7ae467f0d' LIMIT 1",
                "DROP TABLE `analytics`."
                "`_streambuild_target_mutation_lock_release_272812a7ae467f0d` SYNC;",
                "DROP TABLE `analytics`.`_streambuild_target_mutation_lock` SYNC;",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_owned_lock_when_releasing_then_verifies_owner_before_drop(
    test_case: TargetMutationLockReleaseTestCase,
) -> None:
    connection: RecordingTargetMutationLockConnection = RecordingTargetMutationLockConnection(
        owner_rows=((f"streambuild-target-lock-v2:{test_case.lock.owner_id}",),),
    )

    connection.release_target_mutation_lock(test_case.lock)

    assert tuple(connection.statements) == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMutationLockOwnershipChangeTestCase(
            description="lock owner changed before release",
            lock=AdapterTargetMutationLock(database="analytics", owner_id="run-123"),
            current_owner_id="other-run",
            expected_error_message="ownership changed",
            expected_statements=(
                "CREATE TABLE `analytics`."
                "`_streambuild_target_mutation_lock_release_272812a7ae467f0d` "
                "(guard UInt8) ENGINE = TinyLog COMMENT 'streambuild-target-lock-v2:run-123';",
                "EXCHANGE TABLES `analytics`.`_streambuild_target_mutation_lock` AND "
                "`analytics`.`_streambuild_target_mutation_lock_release_272812a7ae467f0d`;",
                "SELECT comment FROM system.tables WHERE database = 'analytics' AND name = "
                "'_streambuild_target_mutation_lock_release_272812a7ae467f0d' LIMIT 1",
                "EXCHANGE TABLES `analytics`.`_streambuild_target_mutation_lock` AND "
                "`analytics`.`_streambuild_target_mutation_lock_release_272812a7ae467f0d`;",
                "DROP TABLE `analytics`."
                "`_streambuild_target_mutation_lock_release_272812a7ae467f0d` SYNC;",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_different_lock_owner_when_releasing_then_refuses_drop(
    test_case: TargetMutationLockOwnershipChangeTestCase,
) -> None:
    connection: RecordingTargetMutationLockConnection = RecordingTargetMutationLockConnection(
        owner_rows=((f"streambuild-target-lock-v2:{test_case.current_owner_id}",),),
    )

    with pytest.raises(
        AdapterTargetMutationLockError,
        match=test_case.expected_error_message,
    ):
        connection.release_target_mutation_lock(test_case.lock)

    assert tuple(connection.statements) == test_case.expected_statements
