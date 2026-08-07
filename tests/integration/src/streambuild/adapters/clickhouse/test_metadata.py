from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Barrier

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterConnectionConfig,
    AdapterCurrentQualityNode,
    AdapterMetadataState,
    AdapterNodeResultRecord,
)
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.integration.src.streambuild.adapters.clickhouse._test_types import (
    LatestNodeStatusIntegrationTestCase,
    MetadataMigrationIntegrationTestCase,
)
from tests.integration.src.streambuild.adapters.clickhouse.helpers import (
    build_invocation_record,
    execute_rendered_statements,
    integer_rows,
    run_metadata_migration,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        MetadataMigrationIntegrationTestCase(
            description="empty metadata state migrates repeatedly without duplicate versions",
            expected_table_names=(
                "_streambuild_direct_fingerprints",
                "_streambuild_invocations",
                "_streambuild_node_results",
                "_streambuild_run_events",
                "_streambuild_schema_versions",
                "_streambuild_virtual_deployments",
                "_streambuild_virtual_object_state",
                "_streambuild_virtual_publications",
                "_streambuild_virtual_replay_boundaries",
            ),
            expected_version_rows=((1,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_database_when_migrating_metadata_repeatedly_then_schema_is_idempotent(
    test_case: MetadataMigrationIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    connection: AdapterConnection = ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        execute_rendered_statements(
            client=clickhouse_client,
            statements=connection.render_migrate_metadata_state(clickhouse_database),
        )
        execute_rendered_statements(
            client=clickhouse_client,
            statements=connection.render_migrate_metadata_state(clickhouse_database),
        )
    finally:
        connection.close()

    table_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT name FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name LIKE '\\_streambuild%' ORDER BY name"
    ).result_rows
    version_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT version FROM {clickhouse_database}._streambuild_schema_versions ORDER BY version"
    ).result_rows

    assert tuple(str(row[0]) for row in table_rows) == test_case.expected_table_names
    assert integer_rows(version_rows) == test_case.expected_version_rows


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        MetadataMigrationIntegrationTestCase(
            description="concurrent metadata migrations converge on one logical version",
            expected_table_names=(
                "_streambuild_direct_fingerprints",
                "_streambuild_invocations",
                "_streambuild_node_results",
                "_streambuild_run_events",
                "_streambuild_schema_versions",
                "_streambuild_virtual_deployments",
                "_streambuild_virtual_object_state",
                "_streambuild_virtual_publications",
                "_streambuild_virtual_replay_boundaries",
            ),
            expected_version_rows=((1,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_database_when_migrating_metadata_concurrently_then_attempts_are_safe(
    test_case: MetadataMigrationIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    start_barrier: Barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures: tuple[Future[None], ...] = (
            executor.submit(
                run_metadata_migration,
                connection_settings=clickhouse_connection_settings,
                database=clickhouse_database,
                start_barrier=start_barrier,
            ),
            executor.submit(
                run_metadata_migration,
                connection_settings=clickhouse_connection_settings,
                database=clickhouse_database,
                start_barrier=start_barrier,
            ),
        )
        _ = tuple(future.result() for future in futures)

    table_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT name FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name LIKE '\\_streambuild%' ORDER BY name"
    ).result_rows
    version_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT DISTINCT version FROM "
        f"{clickhouse_database}._streambuild_schema_versions ORDER BY version"
    ).result_rows

    assert tuple(str(row[0]) for row in table_rows) == test_case.expected_table_names
    assert integer_rows(version_rows) == test_case.expected_version_rows


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        LatestNodeStatusIntegrationTestCase(
            description="latest deterministic results classify current stale and never-run nodes",
            expected_status_rows=(
                ("audits/current.sql:1", "failed"),
                ("audits/never.sql:1", "never_run"),
                ("tests/stale.sql:1", "stale"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_manifest_nodes_and_result_history_when_querying_then_ui_states_are_classified(
    test_case: LatestNodeStatusIntegrationTestCase,
    managed_clickhouse_client: AdapterConnection,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    execute_rendered_statements(
        client=clickhouse_client,
        statements=managed_clickhouse_client.render_migrate_metadata_state(clickhouse_database),
    )
    node_results: tuple[AdapterNodeResultRecord, ...] = (
        AdapterNodeResultRecord(
            result_id="result-a",
            invocation_id="inv-1",
            node_kind="audit",
            node_identity="audits/current.sql:1",
            definition_fingerprint="current-fingerprint",
            target_identity=clickhouse_database,
            status="passed",
            severity="error",
            failure_count=0,
            completed_at="2026-08-02 12:00:00.000",
            payload_json="{}",
            error_message=None,
        ),
        AdapterNodeResultRecord(
            result_id="result-z",
            invocation_id="inv-2",
            node_kind="audit",
            node_identity="audits/current.sql:1",
            definition_fingerprint="current-fingerprint",
            target_identity=clickhouse_database,
            status="failed",
            severity="error",
            failure_count=2,
            completed_at="2026-08-02 12:00:00.000",
            payload_json="{}",
            error_message=None,
        ),
        AdapterNodeResultRecord(
            result_id="result-stale",
            invocation_id="inv-3",
            node_kind="test",
            node_identity="tests/stale.sql:1",
            definition_fingerprint="old-fingerprint",
            target_identity=clickhouse_database,
            status="passed",
            severity=None,
            failure_count=0,
            completed_at="2026-08-02 12:01:00.000",
            payload_json="{}",
            error_message=None,
        ),
        AdapterNodeResultRecord(
            result_id="result-newer-other-fingerprint",
            invocation_id="inv-4",
            node_kind="audit",
            node_identity="audits/current.sql:1",
            definition_fingerprint="other-fingerprint",
            target_identity=clickhouse_database,
            status="passed",
            severity="error",
            failure_count=0,
            completed_at="2026-08-02 12:02:00.000",
            payload_json="{}",
            error_message=None,
        ),
        AdapterNodeResultRecord(
            result_id="result-other-project",
            invocation_id="inv-other-project",
            node_kind="audit",
            node_identity="audits/current.sql:1",
            definition_fingerprint="current-fingerprint",
            target_identity=clickhouse_database,
            status="passed",
            severity="error",
            failure_count=0,
            completed_at="2026-08-02 12:03:00.000",
            payload_json="{}",
            error_message=None,
        ),
    )
    project_identity: str = "/project/current"
    state: AdapterMetadataState = AdapterMetadataState(
        object_states=(),
        deployments=(),
        deployment_watermarks=(),
        publish_events=(),
        invocations=(
            build_invocation_record(
                invocation_id="inv-1",
                project_identity=project_identity,
                target_identity=clickhouse_database,
                completed_at="2026-08-02 12:00:00.000",
            ),
            build_invocation_record(
                invocation_id="inv-2",
                project_identity=project_identity,
                target_identity=clickhouse_database,
                completed_at="2026-08-02 12:00:00.000",
            ),
            build_invocation_record(
                invocation_id="inv-3",
                project_identity=project_identity,
                target_identity=clickhouse_database,
                completed_at="2026-08-02 12:01:00.000",
            ),
            build_invocation_record(
                invocation_id="inv-4",
                project_identity=project_identity,
                target_identity=clickhouse_database,
                completed_at="2026-08-02 12:02:00.000",
            ),
            build_invocation_record(
                invocation_id="inv-other-project",
                project_identity="/project/other",
                target_identity=clickhouse_database,
                completed_at="2026-08-02 12:03:00.000",
            ),
        ),
        node_results=node_results,
    )
    execute_rendered_statements(
        client=clickhouse_client,
        statements=managed_clickhouse_client.render_persist_metadata_state(
            database=clickhouse_database, state=state
        ),
    )
    query: str = managed_clickhouse_client.render_latest_node_status_query(
        database=clickhouse_database,
        project_identity=project_identity,
        target_identity=clickhouse_database,
        nodes=(
            AdapterCurrentQualityNode("audit", "audits/current.sql:1", "current-fingerprint"),
            AdapterCurrentQualityNode("audit", "audits/never.sql:1", "never-fingerprint"),
            AdapterCurrentQualityNode("test", "tests/stale.sql:1", "new-fingerprint"),
        ),
    )
    rows: Sequence[Sequence[object]] = clickhouse_client.query(query).result_rows

    assert tuple((str(row[1]), str(row[3])) for row in rows) == test_case.expected_status_rows
