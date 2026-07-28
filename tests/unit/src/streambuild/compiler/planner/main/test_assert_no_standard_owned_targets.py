import pytest

from streambuild.adapter.models import AdapterOwnershipRecord, AdapterQueryResult
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.planner.exceptions import TargetOwnershipConflictError
from streambuild.compiler.planner.main.assert_no_standard_owned_targets import (
    assert_no_standard_owned_targets,
)
from tests.unit.src.streambuild.compiler.planner.helpers import (
    SnapshotRecordingConnection,
    build_snapshot_catalog,
)
from tests.unit.src.streambuild.compiler.planner.main._test_types import (
    ReciprocalOwnershipDatabaseTestCase,
    ReciprocalOwnershipRejectionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReciprocalOwnershipDatabaseTestCase(
            description="same relation claim in another target database is ignored",
            ownership_database_name="database_a",
            target_database="database_b",
            expected_metadata_reads=("metadata",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_other_database_claim_when_guarding_virtual_environment_then_it_is_allowed(
    test_case: ReciprocalOwnershipDatabaseTestCase,
) -> None:
    connection: SnapshotRecordingConnection = SnapshotRecordingConnection(
        catalog=build_snapshot_catalog(),
        metadata_result=AdapterQueryResult(rows=()),
        virtual_environments=True,
        ownership_records=(
            AdapterOwnershipRecord(
                database_name=test_case.ownership_database_name,
                relation_name="tbl__orders",
                resource_kind="table",
                logical_model_name="orders",
                owning_mode=AdapterOwningMode.STANDARD,
                tool_version="test",
            ),
        ),
    )

    assert_no_standard_owned_targets(
        client=connection,
        metadata_database="metadata",
        target_database=test_case.target_database,
        relation_names=("tbl__orders",),
    )

    assert tuple(connection.ownership_databases) == test_case.expected_metadata_reads


@pytest.mark.parametrize(
    "test_case",
    [
        ReciprocalOwnershipRejectionTestCase(
            description="same relation claim in target database is rejected",
            database_name="database_a",
            expected_error_fragment=(
                "Virtual environments refuse to take over relations owned by standard mode: "
                "tbl__orders"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_database_claim_when_guarding_virtual_environment_then_it_is_rejected(
    test_case: ReciprocalOwnershipRejectionTestCase,
) -> None:
    connection: SnapshotRecordingConnection = SnapshotRecordingConnection(
        catalog=build_snapshot_catalog(),
        metadata_result=AdapterQueryResult(rows=()),
        virtual_environments=True,
        ownership_records=(
            AdapterOwnershipRecord(
                database_name=test_case.database_name,
                relation_name="tbl__orders",
                resource_kind="table",
                logical_model_name="orders",
                owning_mode=AdapterOwningMode.STANDARD,
                tool_version="test",
            ),
        ),
    )

    with pytest.raises(TargetOwnershipConflictError) as rejection:
        assert_no_standard_owned_targets(
            client=connection,
            metadata_database="metadata",
            target_database=test_case.database_name,
            relation_names=("tbl__orders",),
        )

    assert str(rejection.value) == test_case.expected_error_fragment
