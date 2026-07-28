from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.standard.models import StandardReplayBoundary
from tests.integration.src.streambuild.cli._test_types import (
    CliReciprocalOwnershipIntegrationTestCase,
    CliStandardAggregateBuildIntegrationTestCase,
    CliStandardBuildAuditIntegrationTestCase,
    CliStandardBuildBoundaryIntegrationTestCase,
    CliStandardBuildGuardIntegrationTestCase,
    CliStandardBuildIntegrationTestCase,
    CliStandardBuildPartialFailureIntegrationTestCase,
    CliStandardBuildRerunIntegrationTestCase,
    CliStandardExecutionStepFailureIntegrationTestCase,
    CliStandardSelectedAuditIntegrationTestCase,
    CliStandardSelectedBuildIntegrationTestCase,
    CliStandardSelectedFailureIntegrationTestCase,
    CliStandardSelectionMatrixIntegrationTestCase,
)
from tests.integration.src.streambuild.cli.helpers import (
    FailFinalOwnershipOnceConnection,
    FailOnceBoundaryQueryConnection,
    FailOnceDropConnection,
    FailOnceRealizationConnection,
    FailOnceReplayConnection,
    FailOnceViewRealizationConnection,
    FailSecondReplayOnceConnection,
    StandardActionRecordingConnection,
    build_managed_clickhouse_client,
    capture_standard_build_boundaries,
    execute_standard_build_directly,
    execute_warehouse_statements,
    insert_landing_rows,
    insert_landing_rows_after_delay,
    run_standard_build,
    run_virtual_environment_backfill,
    standard_build_order_ids,
    standard_graph_delta_rows,
    standard_graph_order_ids,
    standard_owned_relation_names,
    standard_owned_replay_coverage_ranges,
    warehouse_row_count,
    write_standard_aggregate_project,
    write_standard_build_project,
    write_standard_selected_graph_audits,
    write_standard_selected_graph_project,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardBuildIntegrationTestCase(
            description="a greenfield build replays retained rows and stays live afterwards",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 3), ("order-3", 1, 1)),
            late_landing_rows=(("order-4", 0, 4),),
            expected_created_relations=("tbl__orders_enriched", "mv__orders_enriched"),
            expected_owned_relations=("mv__orders_enriched", "tbl__orders_enriched"),
            expected_replayed_order_ids=("order-1", "order-2", "order-3"),
            expected_final_order_ids=("order-1", "order-2", "order-3", "order-4"),
            expected_deployment_row_count=0,
            expected_stable_view_count=0,
            expected_replay_coverage_ranges=(
                ("_replay_partition=0", "1", "1"),
                ("_replay_partition=0", "3", "3"),
                ("_replay_partition=1", "1", "1"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_retained_landing_rows_when_building_then_history_replays_and_live_rows_follow(
    test_case: CliStandardBuildIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        first_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=connection, database=clickhouse_database, rows=test_case.landing_rows
        )
        second_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        replayed_order_ids: tuple[str, ...] = standard_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
        insert_landing_rows(
            connection=connection, database=clickhouse_database, rows=test_case.late_landing_rows
        )
        final_order_ids: tuple[str, ...] = standard_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
        owned_relation_names: tuple[str, ...] = standard_owned_relation_names(
            connection=connection, database=clickhouse_database
        )
        replay_coverage_ranges: tuple[tuple[str, str, str], ...] = (
            standard_owned_replay_coverage_ranges(
                connection=connection, database=clickhouse_database
            )
        )
    finally:
        connection.close()

    assert (first_exit_code, second_exit_code) == (0, 0)
    assert replayed_order_ids == test_case.expected_replayed_order_ids
    assert final_order_ids == test_case.expected_final_order_ids
    assert owned_relation_names == test_case.expected_owned_relations
    assert replay_coverage_ranges == test_case.expected_replay_coverage_ranges
    assert (
        warehouse_row_count(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            statement="SELECT count() FROM {database}.streambuild_deployments",
        )
        == test_case.expected_deployment_row_count
    )
    assert (
        warehouse_row_count(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            statement=(
                "SELECT count() FROM system.tables "
                "WHERE database = '{database}' AND engine = 'View'"
            ),
        )
        == test_case.expected_stable_view_count
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardBuildBoundaryIntegrationTestCase(
            description="a freshly created target yields one inclusive preserved cutoff",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            pre_capture_statements=("TRUNCATE TABLE {database}.tbl__orders_enriched",),
            expected_boundary_keys=("_replay_partition=0",),
            expected_cutoff_values=("2",),
            expected_cutoff_inclusive=(True,),
        ),
        CliStandardBuildBoundaryIntegrationTestCase(
            description="live rows already in the target yield one exclusive live floor",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            pre_capture_statements=(),
            expected_boundary_keys=("_replay_partition=0",),
            expected_cutoff_values=("1",),
            expected_cutoff_inclusive=(False,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_live_and_preserved_rows_when_capturing_boundaries_then_one_contract_is_used(
    test_case: CliStandardBuildBoundaryIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
) -> None:
    write_standard_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=connection, database=clickhouse_database, rows=test_case.landing_rows
        )
        execute_warehouse_statements(
            connection=connection,
            database=clickhouse_database,
            statements=test_case.pre_capture_statements,
        )
        boundaries: tuple[StandardReplayBoundary, ...] = capture_standard_build_boundaries(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
    finally:
        connection.close()

    assert (
        tuple(boundary.boundary_key for boundary in boundaries) == test_case.expected_boundary_keys
    )
    assert (
        tuple(boundary.cutoff_value for boundary in boundaries) == test_case.expected_cutoff_values
    )
    assert (
        tuple(boundary.cutoff_inclusive for boundary in boundaries)
        == test_case.expected_cutoff_inclusive
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardBuildGuardIntegrationTestCase(
            description="managed Kafka drift blocks the build before any model teardown",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            rebuilt_topic="source.orders.renamed",
            pre_rebuild_statements=(),
            expected_exit_code=1,
            expected_error_fragment="Standard build preserves managed source infrastructure",
            expected_order_ids=("order-1", "order-2"),
        ),
        CliStandardBuildGuardIntegrationTestCase(
            description="an interior replay gap blocks the rerun before teardown",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2), ("order-3", 0, 3)),
            rebuilt_topic="source.orders",
            pre_rebuild_statements=(
                "ALTER TABLE {database}.raw__orders DELETE WHERE _replay_offset = 2 "
                "SETTINGS mutations_sync = 2",
            ),
            expected_exit_code=1,
            expected_error_fragment="no longer covers the required replay range",
            expected_order_ids=("order-1", "order-2", "order-3"),
        ),
        CliStandardBuildGuardIntegrationTestCase(
            description="an aged-out driving input blocks the rerun with explicit guidance",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            rebuilt_topic="source.orders",
            pre_rebuild_statements=(
                "ALTER TABLE {database}.raw__orders DELETE WHERE _replay_offset <= 1 "
                "SETTINGS mutations_sync = 2",
            ),
            expected_exit_code=1,
            expected_error_fragment=(
                "Standard rerun would silently drop retained history because the preserved "
                "driving input no longer covers the required replay range"
            ),
            expected_order_ids=("order-1", "order-2"),
        ),
        CliStandardBuildGuardIntegrationTestCase(
            description="a target without its ownership record blocks the build as unmanaged",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            rebuilt_topic="source.orders",
            pre_rebuild_statements=("TRUNCATE TABLE {database}.streambuild_target_ownership",),
            expected_exit_code=1,
            expected_error_fragment="Standard mode refuses to replace relations it does not own",
            expected_order_ids=("order-1", "order-2"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_warehouse_state_when_building_then_it_blocks_before_teardown(
    test_case: CliStandardBuildGuardIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=connection, database=clickhouse_database, rows=test_case.landing_rows
        )
        execute_warehouse_statements(
            connection=connection,
            database=clickhouse_database,
            statements=test_case.pre_rebuild_statements,
        )
        write_standard_build_project(project_root=tmp_path, topic=test_case.rebuilt_topic)
        exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        command_error: str = capsys.readouterr().err
        order_ids: tuple[str, ...] = standard_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        connection.close()

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_error_fragment in command_error
    assert order_ids == test_case.expected_order_ids


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliReciprocalOwnershipIntegrationTestCase(
            description="virtual-environment backfill refuses a standard-owned target",
            expected_exit_code=1,
            expected_error_fragment=(
                "Virtual environments refuse to take over relations owned by standard mode"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_standard_owned_targets_when_backfilling_then_virtual_environments_are_rejected(
    test_case: CliReciprocalOwnershipIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
) -> None:
    write_standard_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        build_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        backfill_exit_code: int = run_virtual_environment_backfill(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        backfill_error: str = capsys.readouterr().err
    finally:
        connection.close()

    assert build_exit_code == 0
    assert backfill_exit_code == test_case.expected_exit_code
    assert test_case.expected_error_fragment in backfill_error


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliReciprocalOwnershipIntegrationTestCase(
            description="standard build refuses a virtual-environment target",
            expected_exit_code=1,
            expected_error_fragment="Standard mode refuses to replace relations it does not own",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_environment_target_when_building_standard_then_it_is_rejected(
    test_case: CliReciprocalOwnershipIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
) -> None:
    write_standard_build_project(project_root=tmp_path, virtual_environments=True)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        backfill_exit_code: int = run_virtual_environment_backfill(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        write_standard_build_project(project_root=tmp_path)
        build_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        build_error: str = capsys.readouterr().err
    finally:
        connection.close()

    assert backfill_exit_code == 0
    assert build_exit_code == test_case.expected_exit_code
    assert test_case.expected_error_fragment in build_error


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardBuildAuditIntegrationTestCase(
            description="a failing audit fails the command while the built rows remain live",
            audit_sql_by_name=(
                (
                    "no_empty_order_ids.sql",
                    'AUDIT (\n  description: "order ids must not be empty",\n);\n\n'
                    'SELECT order_id\nFROM __ref("orders_enriched")\n'
                    "WHERE order_id != ''\n",
                ),
            ),
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            late_landing_rows=(("order-3", 0, 3),),
            expected_exit_code=1,
            expected_stdout_fragment="FAIL",
            expected_final_order_ids=("order-1", "order-2", "order-3"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_audit_when_building_then_command_fails_without_rollback(
    test_case: CliStandardBuildAuditIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=connection, database=clickhouse_database, rows=test_case.landing_rows
        )
        connection.command(f"TRUNCATE TABLE {clickhouse_database}.tbl__orders_enriched")
        write_standard_build_project(
            project_root=tmp_path, audit_sql_by_name=test_case.audit_sql_by_name
        )
        exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            json_output=False,
        )
        command_output: str = capsys.readouterr().out
        insert_landing_rows(
            connection=connection,
            database=clickhouse_database,
            rows=test_case.late_landing_rows,
        )
        final_order_ids: tuple[str, ...] = standard_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        connection.close()

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stdout_fragment in command_output
    assert final_order_ids == test_case.expected_final_order_ids


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardBuildRerunIntegrationTestCase(
            description="a rerun after creation failure completes the closure deterministically",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            restored_landing_rows=(("order-1", 0, 1),),
            late_landing_rows=(("order-3", 0, 3),),
            expected_failed_exit_code=1,
            expected_incomplete_target_count=0,
            expected_retention_exit_code=1,
            expected_retention_error_fragment="no longer covers the required replay range",
            expected_rerun_exit_code=0,
            expected_final_order_ids=("order-1", "order-2", "order-3"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_creation_failure_when_rerunning_then_the_closure_completes(
    test_case: CliStandardBuildRerunIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_build_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=delegate, database=clickhouse_database, rows=test_case.landing_rows
        )
        connection: AdapterConnection = FailOnceRealizationConnection(delegate)
        failed_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        incomplete_target_count: int = warehouse_row_count(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            statement=(
                "SELECT count() FROM system.tables WHERE database = '{database}' "
                "AND name = 'tbl__orders_enriched'"
            ),
        )
        connection.command(
            f"ALTER TABLE {clickhouse_database}.raw__orders DELETE WHERE _replay_offset <= 1 "
            "SETTINGS mutations_sync = 2"
        )
        retention_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        retention_error: str = capsys.readouterr().err
        insert_landing_rows(
            connection=connection,
            database=clickhouse_database,
            rows=test_case.restored_landing_rows,
        )
        rerun_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=connection,
            database=clickhouse_database,
            rows=test_case.late_landing_rows,
        )
        final_order_ids: tuple[str, ...] = standard_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        delegate.close()

    assert failed_exit_code == test_case.expected_failed_exit_code
    assert incomplete_target_count == test_case.expected_incomplete_target_count
    assert retention_exit_code == test_case.expected_retention_exit_code
    assert test_case.expected_retention_error_fragment in retention_error
    assert rerun_exit_code == test_case.expected_rerun_exit_code
    assert final_order_ids == test_case.expected_final_order_ids


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardBuildPartialFailureIntegrationTestCase(
            description="partial live target cannot narrow durable replay coverage",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            partial_landing_rows=(("order-3", 0, 3),),
            expected_failed_exit_code=1,
            expected_retention_exit_code=1,
            expected_retention_error_fragment="no longer covers the required replay range",
            expected_partial_order_ids=("order-3",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_target_after_failure_when_rerunning_then_durable_coverage_is_kept(
    test_case: CliStandardBuildPartialFailureIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_build_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=delegate, database=clickhouse_database, rows=test_case.landing_rows
        )
        connection: AdapterConnection = FailOnceReplayConnection(delegate)
        failed_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=connection,
            database=clickhouse_database,
            rows=test_case.partial_landing_rows,
        )
        connection.command(
            f"ALTER TABLE {clickhouse_database}.raw__orders DELETE WHERE _replay_offset <= 1 "
            "SETTINGS mutations_sync = 2"
        )
        retention_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        retention_error: str = capsys.readouterr().err
        partial_order_ids: tuple[str, ...] = standard_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        delegate.close()

    assert failed_exit_code == test_case.expected_failed_exit_code
    assert retention_exit_code == test_case.expected_retention_exit_code
    assert test_case.expected_retention_error_fragment in retention_error
    assert partial_order_ids == test_case.expected_partial_order_ids


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardSelectedBuildIntegrationTestCase(
            description="selected fan-in closure rebuilds once and repeats when unchanged",
            selectors=("beta",),
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            boundary_landing_rows=(("order-3", 0, 3),),
            expected_order_ids=("order-1", "order-2", "order-3"),
            expected_delta_rows=(
                ("order-1", "order-1-gamma"),
                ("order-2", "order-2-gamma"),
                ("order-3", "order-3-gamma"),
            ),
            expected_drop_statements=(
                "DROP TABLE IF EXISTS {database}.mv__delta SYNC",
                "DROP TABLE IF EXISTS {database}.mv__gamma SYNC",
                "DROP TABLE IF EXISTS {database}.mv__beta SYNC",
                "DROP TABLE IF EXISTS {database}.tbl__delta SYNC",
                "DROP TABLE IF EXISTS {database}.tbl__gamma SYNC",
                "DROP TABLE IF EXISTS {database}.tbl__beta SYNC",
            ),
            expected_realized_relation_names=(
                "tbl__beta",
                "tbl__gamma",
                "tbl__delta",
                "mv__beta",
                "mv__gamma",
                "mv__delta",
            ),
            expected_replay_targets=("tbl__beta", "tbl__gamma", "tbl__delta"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_settled_graph_when_building_selected_model_then_closure_rebuilds_once(
    test_case: CliStandardSelectedBuildIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=delegate, database=clickhouse_database, rows=test_case.landing_rows
        )
        prerequisite_before: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="alpha",
        )
        connection: StandardActionRecordingConnection = StandardActionRecordingConnection(delegate)
        with ThreadPoolExecutor(max_workers=1) as executor:
            boundary_future: Future[None] = executor.submit(
                insert_landing_rows_after_delay,
                connection_settings=clickhouse_connection_settings,
                database=clickhouse_database,
                rows=test_case.boundary_landing_rows,
                delay_seconds=0.2,
            )
            _ = execute_standard_build_directly(
                project_root=tmp_path,
                database=clickhouse_database,
                connection=connection,
                stabilization_seconds=1.0,
                selectors=test_case.selectors,
            )
            _ = boundary_future.result()
        repeated_exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        _ = capsys.readouterr()
        prerequisite_after: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="alpha",
        )
        beta_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
        gamma_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="gamma",
        )
        delta_rows: tuple[tuple[str, str], ...] = standard_graph_delta_rows(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        delegate.close()

    expected_drop_statements: tuple[str, ...] = tuple(
        statement.format(database=clickhouse_database)
        for statement in test_case.expected_drop_statements
    )
    assert initial_exit_code == 0
    assert repeated_exit_code == 0
    assert prerequisite_before == test_case.expected_order_ids[:-1]
    assert prerequisite_after == test_case.expected_order_ids
    assert beta_rows == test_case.expected_order_ids
    assert gamma_rows == test_case.expected_order_ids
    assert delta_rows == test_case.expected_delta_rows
    assert tuple(
        connection.command_statements.count(statement) for statement in expected_drop_statements
    ) == (2, 2, 2, 2, 2, 2)
    assert tuple(connection.realized_relation_names) == (
        *test_case.expected_realized_relation_names,
        *test_case.expected_realized_relation_names,
    )
    assert tuple(connection.replay_targets) == (
        *test_case.expected_replay_targets,
        *test_case.expected_replay_targets,
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardAggregateBuildIntegrationTestCase(
            description="aggregate root is rejected before selected writes",
            selectors=("beta",),
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            expected_error_fragment=(
                "Standard mode cannot safely rebuild aggregate models without an atomic "
                "replay/live frontier: beta"
            ),
            expected_preserved_order_ids=("order-1", "order-2"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_aggregate_root_when_building_selected_model_then_it_rejects_before_writes(
    test_case: CliStandardAggregateBuildIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=delegate,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        write_standard_aggregate_project(project_root=tmp_path)
        connection: StandardActionRecordingConnection = StandardActionRecordingConnection(delegate)
        rejected_exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        rejection_error: str = capsys.readouterr().err
        preserved_order_ids: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
    finally:
        delegate.close()

    assert (initial_exit_code, rejected_exit_code) == (0, 1)
    assert test_case.expected_error_fragment in rejection_error
    assert preserved_order_ids == test_case.expected_preserved_order_ids
    assert connection.command_statements == []
    assert connection.realized_relation_names == []
    assert connection.replay_targets == []


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardSelectedFailureIntegrationTestCase(
            description="second selected population failure reconstructs exactly on retry",
            selectors=("beta",),
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            expected_order_ids=("order-1", "order-2"),
            expected_delta_rows=(
                ("order-1", "order-1-gamma"),
                ("order-2", "order-2-gamma"),
            ),
            expected_failure_fragment="injected failure during second population segment",
            expected_replay_targets=(
                "tbl__beta",
                "tbl__gamma",
                "tbl__beta",
                "tbl__gamma",
                "tbl__delta",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_selected_population_when_retrying_then_closure_reconstructs_exactly(
    test_case: CliStandardSelectedFailureIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=delegate, database=clickhouse_database, rows=test_case.landing_rows
        )
        connection: FailSecondReplayOnceConnection = FailSecondReplayOnceConnection(delegate)
        failed_exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        failure_error: str = capsys.readouterr().err
        rerun_exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        rerun_error: str = capsys.readouterr().err
        beta_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
        gamma_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="gamma",
        )
        delta_rows: tuple[tuple[str, str], ...] = standard_graph_delta_rows(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        delegate.close()

    assert (initial_exit_code, failed_exit_code, rerun_exit_code) == (0, 1, 0)
    assert test_case.expected_failure_fragment in failure_error
    assert rerun_error == ""
    assert (beta_rows, gamma_rows) == (
        test_case.expected_order_ids,
        test_case.expected_order_ids,
    )
    assert delta_rows == test_case.expected_delta_rows
    assert tuple(connection.replay_targets) == test_case.expected_replay_targets


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardExecutionStepFailureIntegrationTestCase(
            description="teardown failure is safe to retry",
            connection_factory=FailOnceDropConnection,
            expected_failure_fragment="injected failure during selected teardown",
        ),
        CliStandardExecutionStepFailureIntegrationTestCase(
            description="view attachment failure is safe to retry",
            connection_factory=FailOnceViewRealizationConnection,
            expected_failure_fragment="injected failure during selected view attachment",
        ),
        CliStandardExecutionStepFailureIntegrationTestCase(
            description="boundary capture failure is safe to retry",
            connection_factory=FailOnceBoundaryQueryConnection,
            expected_failure_fragment="injected failure during selected boundary capture",
        ),
        CliStandardExecutionStepFailureIntegrationTestCase(
            description="final ownership failure is safe to retry",
            connection_factory=FailFinalOwnershipOnceConnection,
            expected_failure_fragment="injected failure during final ownership persistence",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selected_execution_step_failure_when_retrying_then_result_is_exact(
    test_case: CliStandardExecutionStepFailureIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=delegate,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        connection: AdapterConnection = test_case.connection_factory(delegate)
        failed_exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=("beta",),
        )
        failure_error: str = capsys.readouterr().err
        rerun_exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=("beta",),
        )
        rerun_error: str = capsys.readouterr().err
        beta_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
        gamma_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="gamma",
        )
        delta_rows: tuple[tuple[str, str], ...] = standard_graph_delta_rows(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        delegate.close()

    assert (initial_exit_code, failed_exit_code, rerun_exit_code) == (0, 1, 0)
    assert test_case.expected_failure_fragment in failure_error
    assert rerun_error == ""
    assert (beta_rows, gamma_rows) == (
        ("order-1", "order-2"),
        ("order-1", "order-2"),
    )
    assert delta_rows == (
        ("order-1", "order-1-gamma"),
        ("order-2", "order-2-gamma"),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardSelectionMatrixIntegrationTestCase(
            description="head selection rebuilds every model",
            selectors=("alpha",),
            expected_drop_relation_names=(
                "mv__delta",
                "mv__gamma",
                "mv__beta",
                "mv__alpha",
                "tbl__delta",
                "tbl__gamma",
                "tbl__beta",
                "tbl__alpha",
            ),
            expected_replay_targets=(
                "tbl__alpha",
                "tbl__beta",
                "tbl__gamma",
                "tbl__delta",
            ),
        ),
        CliStandardSelectionMatrixIntegrationTestCase(
            description="side-reference selection rebuilds its dependent closure",
            selectors=("gamma",),
            expected_drop_relation_names=(
                "mv__delta",
                "mv__gamma",
                "tbl__delta",
                "tbl__gamma",
            ),
            expected_replay_targets=("tbl__gamma", "tbl__delta"),
        ),
        CliStandardSelectionMatrixIntegrationTestCase(
            description="leaf selection rebuilds only the leaf",
            selectors=("delta",),
            expected_drop_relation_names=("mv__delta", "tbl__delta"),
            expected_replay_targets=("tbl__delta",),
        ),
        CliStandardSelectionMatrixIntegrationTestCase(
            description="overlapping selections execute each model once",
            selectors=("gamma", "delta"),
            expected_drop_relation_names=(
                "mv__delta",
                "mv__gamma",
                "tbl__delta",
                "tbl__gamma",
            ),
            expected_replay_targets=("tbl__gamma", "tbl__delta"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selection_matrix_when_building_then_exact_closure_is_reconstructed(
    test_case: CliStandardSelectionMatrixIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_standard_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=delegate,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        connection: StandardActionRecordingConnection = StandardActionRecordingConnection(delegate)
        selected_exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        selected_error: str = capsys.readouterr().err
        alpha_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="alpha",
        )
        beta_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
        gamma_rows: tuple[str, ...] = standard_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="gamma",
        )
        delta_rows: tuple[tuple[str, str], ...] = standard_graph_delta_rows(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        delegate.close()

    expected_drop_statements: tuple[str, ...] = tuple(
        f"DROP TABLE IF EXISTS {clickhouse_database}.{name} SYNC"
        for name in test_case.expected_drop_relation_names
    )
    assert (initial_exit_code, selected_exit_code) == (0, 0)
    assert selected_error == ""
    assert tuple(connection.command_statements) == expected_drop_statements
    assert tuple(connection.replay_targets) == test_case.expected_replay_targets
    assert (alpha_rows, beta_rows, gamma_rows) == (
        ("order-1", "order-2"),
        ("order-1", "order-2"),
        ("order-1", "order-2"),
    )
    assert delta_rows == (
        ("order-1", "order-1-gamma"),
        ("order-2", "order-2-gamma"),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardSelectedAuditIntegrationTestCase(
            description="selected build runs only audits fully covered by execution scope",
            selectors=("beta",),
            audit_sql_by_name=(
                (
                    "covered.sql",
                    'AUDIT (description: "covered");\n'
                    "SELECT 'covered-audit-marker' AS marker "
                    'FROM __ref("beta") WHERE 0\n',
                ),
                (
                    "excluded.sql",
                    'AUDIT (description: "excluded");\n'
                    "SELECT 'excluded-audit-marker' AS marker "
                    'FROM __ref("alpha")\n',
                ),
            ),
            expected_query_markers=(
                ("covered-audit-marker", True),
                ("excluded-audit-marker", False),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_build_audits_when_building_then_only_covered_audits_run(
    test_case: CliStandardSelectedAuditIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
) -> None:
    write_standard_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_standard_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            connection=delegate,
            database=clickhouse_database,
            rows=(("order-1", 0, 1),),
        )
        write_standard_selected_graph_audits(
            project_root=tmp_path, audit_sql_by_name=test_case.audit_sql_by_name
        )
        connection: StandardActionRecordingConnection = StandardActionRecordingConnection(delegate)
        selected_exit_code: int = run_standard_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        selected_error: str = capsys.readouterr().err
    finally:
        delegate.close()

    executed_queries: str = "\n".join(connection.query_statements)
    assert (initial_exit_code, selected_exit_code) == (0, 0)
    assert selected_error == ""
    assert (
        tuple(
            (marker, marker in executed_queries) for marker, _ in test_case.expected_query_markers
        )
        == test_case.expected_query_markers
    )
