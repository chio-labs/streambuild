from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.standard.models import StandardReplayBoundary
from tests.integration.src.streambuild.cli._test_types import (
    CliReciprocalOwnershipIntegrationTestCase,
    CliStandardBuildBoundaryIntegrationTestCase,
    CliStandardBuildGuardIntegrationTestCase,
    CliStandardBuildIntegrationTestCase,
)
from tests.integration.src.streambuild.cli.helpers import (
    build_managed_clickhouse_client,
    capture_standard_build_boundaries,
    execute_warehouse_statements,
    insert_landing_rows,
    run_standard_build,
    run_virtual_environment_backfill,
    standard_build_order_ids,
    standard_owned_relation_names,
    warehouse_row_count,
    write_standard_build_project,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliStandardBuildIntegrationTestCase(
            description="a greenfield build replays retained rows and stays live afterwards",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2), ("order-3", 1, 1)),
            late_landing_rows=(("order-4", 0, 3),),
            expected_created_relations=("tbl__orders_enriched", "mv__orders_enriched"),
            expected_owned_relations=("mv__orders_enriched", "tbl__orders_enriched"),
            expected_replayed_order_ids=("order-1", "order-2", "order-3"),
            expected_final_order_ids=("order-1", "order-2", "order-3", "order-4"),
            expected_deployment_row_count=0,
            expected_stable_view_count=0,
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
    finally:
        connection.close()

    assert (first_exit_code, second_exit_code) == (0, 0)
    assert replayed_order_ids == test_case.expected_replayed_order_ids
    assert final_order_ids == test_case.expected_final_order_ids
    assert owned_relation_names == test_case.expected_owned_relations
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
