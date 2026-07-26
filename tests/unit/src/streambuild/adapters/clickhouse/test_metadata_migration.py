from typing import cast

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterQueryResult
from streambuild.adapters.clickhouse._helpers.metadata import (
    migrate_clickhouse_metadata_state,
)
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    MetadataMigrationIdempotenceTestCase,
    MetadataMigrationInterruptionTestCase,
)
from tests.unit.src.streambuild.adapters.clickhouse.helpers import (
    RecordingMetadataMigrationConnection,
    accept_migration_statement,
    migration_schema_result,
    reject_migration_statement,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MetadataMigrationIdempotenceTestCase(
            description="repeated migration applies and records the current version once",
            expected_version_insert_count=1,
            expected_database_ensure_count=2,
            expected_schema_version_ddl_fragment=(
                "CREATE TABLE IF NOT EXISTS metadata.streambuild_state_schema_versions"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_current_migration_when_applied_repeatedly_then_it_is_idempotent(
    test_case: MetadataMigrationIdempotenceTestCase,
) -> None:
    connection: RecordingMetadataMigrationConnection = RecordingMetadataMigrationConnection(
        query_results=(
            AdapterQueryResult(rows=()),
            migration_schema_result(),
            AdapterQueryResult(rows=((1,),)),
        ),
        command_actions=(accept_migration_statement,) * 9,
    )

    migrate_clickhouse_metadata_state(
        connection=cast(AdapterConnection, connection), database="metadata"
    )
    migrate_clickhouse_metadata_state(
        connection=cast(AdapterConnection, connection), database="metadata"
    )

    assert len(connection.inserted_rows) == test_case.expected_version_insert_count
    assert len(connection.ensured_databases) == test_case.expected_database_ensure_count
    assert test_case.expected_schema_version_ddl_fragment in connection.commands[0]


@pytest.mark.parametrize(
    "test_case",
    [
        MetadataMigrationInterruptionTestCase(
            description="interrupted migration remains unrecorded and succeeds on retry",
            expected_version_inserts_before_recovery=0,
            expected_version_inserts_after_recovery=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_migration_when_retried_then_it_recovers_before_recording_version(
    test_case: MetadataMigrationInterruptionTestCase,
) -> None:
    connection: RecordingMetadataMigrationConnection = RecordingMetadataMigrationConnection(
        query_results=(
            AdapterQueryResult(rows=()),
            AdapterQueryResult(rows=()),
            migration_schema_result(),
        ),
        command_actions=(
            accept_migration_statement,
            reject_migration_statement,
            *(accept_migration_statement,) * 8,
        ),
    )

    with pytest.raises(RuntimeError):
        migrate_clickhouse_metadata_state(
            connection=cast(AdapterConnection, connection), database="metadata"
        )

    assert len(connection.inserted_rows) == test_case.expected_version_inserts_before_recovery

    migrate_clickhouse_metadata_state(
        connection=cast(AdapterConnection, connection), database="metadata"
    )

    assert len(connection.inserted_rows) == test_case.expected_version_inserts_after_recovery
