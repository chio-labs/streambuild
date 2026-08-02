import json
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import cast

import pytest
from _pytest.capture import CaptureResult
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterReplayRequest, CatalogRelation
from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.executor.direct.models import DirectBuildResult, DirectReplayBoundary
from streambuild.executor.workflow.models import PublishedBuildWorkflow
from tests.integration.src.streambuild.cli._test_types import (
    CliDirectAdoptedSourceFailureIntegrationTestCase,
    CliDirectAdoptedSourceIntegrationTestCase,
    CliDirectAdoptedStartTimeIntegrationTestCase,
    CliDirectAggregateBuildIntegrationTestCase,
    CliDirectBuildAuditIntegrationTestCase,
    CliDirectBuildBoundaryIntegrationTestCase,
    CliDirectBuildGuardIntegrationTestCase,
    CliDirectBuildIntegrationTestCase,
    CliDirectBuildPartialFailureIntegrationTestCase,
    CliDirectBuildRerunIntegrationTestCase,
    CliDirectExecutionStepFailureIntegrationTestCase,
    CliDirectFutureSourceStartTimeIntegrationTestCase,
    CliDirectLandedAtClockIntegrationTestCase,
    CliDirectLandedAtStartTimeIntegrationTestCase,
    CliDirectManualWorkflowIntegrationTestCase,
    CliDirectRelationRenameIntegrationTestCase,
    CliDirectSelectedAuditIntegrationTestCase,
    CliDirectSelectedBuildIntegrationTestCase,
    CliDirectSelectedFailureIntegrationTestCase,
    CliDirectSelectionMatrixIntegrationTestCase,
    CliDirectStartTimeIntegrationTestCase,
    CliDirectViewBuildIntegrationTestCase,
    CliReciprocalOwnershipIntegrationTestCase,
)
from tests.integration.src.streambuild.cli.helpers import (
    AdoptedLiveInsertConnection,
    DirectActionRecordingConnection,
    FailFinalOwnershipOnceConnection,
    FailOnceBoundaryQueryConnection,
    FailOnceDropConnection,
    FailOnceRealizationConnection,
    FailOnceReplayConnection,
    FailOnceViewRealizationConnection,
    FailSecondReplayOnceConnection,
    ManagedLiveInsertConnection,
    build_managed_clickhouse_client,
    direct_build_order_ids,
    direct_graph_delta_rows,
    direct_graph_order_ids,
    direct_owned_relation_names,
    direct_owned_replay_coverage_ranges,
    direct_relation_order_ids,
    execute_clickhouse_client_sql,
    execute_direct_build_directly,
    execute_warehouse_statements,
    insert_landing_rows,
    insert_landing_rows_after_delay,
    publish_direct_workflow,
    read_workflow_artifact,
    run_direct_build,
    run_direct_plan,
    run_virtual_environment_build,
    stringify_warehouse_rows,
    warehouse_row_count,
    write_direct_adopted_source_project,
    write_direct_aggregate_project,
    write_direct_build_project,
    write_direct_selected_graph_audits,
    write_direct_selected_graph_project,
    write_direct_view_project,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings

_ADOPTED_SOURCE_TEST_CASES: tuple[CliDirectAdoptedSourceIntegrationTestCase, ...] = (
    CliDirectAdoptedSourceIntegrationTestCase(
        description="offset adopted source rebuilds through mapped columns",
        source_yml=(
            "sources:\n"
            "  - kind: stream_table\n"
            "    name: orders\n"
            "    table_name: orders_existing\n"
            "    replay_boundary:\n"
            "      mode: offsets\n"
            "      columns:\n"
            "        _replay_partition: event_partition\n"
            "        _replay_offset: event_offset\n"
            "        _replay_timestamp: event_timestamp\n"
        ),
        model_sql=(
            'MODEL (\n  engine "MergeTree()",\n  order_by ["order_id"]\n);\n'
            "SELECT order_id::String AS order_id, "
            "_replay_partition::Int32 AS _replay_partition, "
            '_replay_offset::Int64 AS _replay_offset FROM __ref("orders")\n'
        ),
        source_columns_sql=(
            "order_id String, event_partition Int32, event_offset Int64, "
            "event_timestamp DateTime64(3)"
        ),
        initial_values_sql=(
            "('order-1', 0, 1, '2026-07-28 00:00:01.000'), "
            "('order-2', 0, 2, '2026-07-28 00:00:02.000')"
        ),
        live_values_sql="('order-3', 0, 3, '2026-07-28 00:00:03.000')",
        source_projection_sql=(
            "order_id, toString(event_partition), toString(event_offset), toString(event_timestamp)"
        ),
        expected_source_rows=(
            ("order-1", "0", "1", "2026-07-28 00:00:01.000"),
            ("order-2", "0", "2", "2026-07-28 00:00:02.000"),
            ("order-3", "0", "3", "2026-07-28 00:00:03.000"),
        ),
        expected_order_ids=("order-1", "order-2", "order-3"),
        expected_replay_mode="offsets",
        expected_replay_columns=(
            "event_partition",
            "event_offset",
            "event_timestamp",
            "event_timestamp",
            "_replay_cursor",
        ),
    ),
    CliDirectAdoptedSourceIntegrationTestCase(
        description="timestamp adopted source rebuilds through mapped columns",
        source_yml=(
            "sources:\n"
            "  - kind: stream_table\n"
            "    name: orders\n"
            "    table_name: orders_existing\n"
            "    replay_boundary:\n"
            "      mode: timestamp\n"
            "      columns:\n"
            "        _replay_timestamp: event_timestamp\n"
        ),
        model_sql=(
            'MODEL (\n  engine "MergeTree()",\n  order_by ["order_id"]\n);\n'
            "SELECT order_id::String AS order_id, "
            "_replay_timestamp::DateTime64(3) AS _replay_timestamp "
            'FROM __ref("orders")\n'
        ),
        source_columns_sql="order_id String, event_timestamp DateTime64(3)",
        initial_values_sql=(
            "('order-1', '2026-07-28 00:00:01.000'), ('order-2', '2026-07-28 00:00:02.000')"
        ),
        live_values_sql="('order-3', '2026-07-28 00:00:03.000')",
        source_projection_sql="order_id, toString(event_timestamp)",
        expected_source_rows=(
            ("order-1", "2026-07-28 00:00:01.000"),
            ("order-2", "2026-07-28 00:00:02.000"),
            ("order-3", "2026-07-28 00:00:03.000"),
        ),
        expected_order_ids=("order-1", "order-2", "order-3"),
        expected_replay_mode="timestamp",
        expected_replay_columns=(
            "_replay_partition",
            "_replay_offset",
            "event_timestamp",
            "event_timestamp",
            "_replay_cursor",
        ),
    ),
    CliDirectAdoptedSourceIntegrationTestCase(
        description="cursor adopted source rebuilds through mapped columns",
        source_yml=(
            "sources:\n"
            "  - kind: stream_table\n"
            "    name: orders\n"
            "    table_name: orders_existing\n"
            "    replay_boundary:\n"
            "      mode: cursor\n"
            "      columns:\n"
            "        _replay_cursor: event_cursor\n"
            "        _replay_timestamp: event_timestamp\n"
        ),
        model_sql=(
            'MODEL (\n  engine "MergeTree()",\n  order_by ["order_id"]\n);\n'
            "SELECT order_id::String AS order_id, "
            '_replay_cursor::UInt64 AS _replay_cursor FROM __ref("orders")\n'
        ),
        source_columns_sql=("order_id String, event_cursor UInt64, event_timestamp DateTime64(3)"),
        initial_values_sql=(
            "('order-1', 1, '2026-07-28 00:00:01.000'), ('order-2', 2, '2026-07-28 00:00:02.000')"
        ),
        live_values_sql="('order-3', 3, '2026-07-28 00:00:03.000')",
        source_projection_sql="order_id, toString(event_cursor), toString(event_timestamp)",
        expected_source_rows=(
            ("order-1", "1", "2026-07-28 00:00:01.000"),
            ("order-2", "2", "2026-07-28 00:00:02.000"),
            ("order-3", "3", "2026-07-28 00:00:03.000"),
        ),
        expected_order_ids=("order-1", "order-2", "order-3"),
        expected_replay_mode="cursor",
        expected_replay_columns=(
            "_replay_partition",
            "_replay_offset",
            "event_timestamp",
            "event_timestamp",
            "event_cursor",
        ),
    ),
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectBuildIntegrationTestCase(
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
            expected_warehouse_written_rows=(3,),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_retained_landing_rows_when_building_then_history_replays_and_live_rows_follow(
    test_case: CliDirectBuildIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        first_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        second_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        second_output: str = capsys.readouterr().out
        second_payload: dict[str, object] = json.loads(second_output)
        replay_payloads: list[dict[str, object]] = cast(
            list[dict[str, object]], second_payload["replays"]
        )
        replayed_order_ids: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.late_landing_rows,
        )
        final_order_ids: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
        owned_relation_names: tuple[str, ...] = direct_owned_relation_names(
            connection=connection, database=clickhouse_database
        )
        replay_coverage_ranges: tuple[tuple[str, str, str], ...] = (
            direct_owned_replay_coverage_ranges(connection=connection, database=clickhouse_database)
        )
    finally:
        connection.close()

    assert (first_exit_code, second_exit_code) == (0, 0)
    assert replayed_order_ids == test_case.expected_replayed_order_ids
    assert final_order_ids == test_case.expected_final_order_ids
    assert owned_relation_names == test_case.expected_owned_relations
    assert replay_coverage_ranges == test_case.expected_replay_coverage_ranges
    assert tuple(payload["warehouse_written_rows"] for payload in replay_payloads) == (
        test_case.expected_warehouse_written_rows
    )
    assert (
        warehouse_row_count(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            statement="SELECT count() FROM {database}._streambuild_virtual_deployments",
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
        CliDirectAdoptedStartTimeIntegrationTestCase(
            description=f"{case.expected_replay_mode} adopted replay is bounded without seeding",
            source_yml=case.source_yml,
            model_sql=case.model_sql,
            source_columns_sql=case.source_columns_sql,
            values_sql=f"{case.initial_values_sql}, {case.live_values_sql}",
            expected_order_ids=("order-2", "order-3"),
            expected_coverage=expected_coverage,
        )
        for case, expected_coverage in zip(
            _ADOPTED_SOURCE_TEST_CASES,
            (
                (("_replay_partition=0", "2", "3"),),
                (
                    (
                        "_replay_timestamp",
                        "2026-07-28 00:00:02.000",
                        "2026-07-28 00:00:03.000",
                    ),
                ),
                (("_replay_cursor", "2", "3"),),
            ),
            strict=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adopted_source_when_building_from_start_time_then_each_mode_is_bounded(
    test_case: CliDirectAdoptedStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_adopted_source_project(
        project_root=tmp_path,
        source_yml=test_case.source_yml,
        model_sql=test_case.model_sql,
    )
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.orders_existing "
            f"({test_case.source_columns_sql}) ENGINE = MergeTree() ORDER BY order_id"
        )
        clickhouse_client.command(
            f"INSERT INTO {clickhouse_database}.orders_existing VALUES {test_case.values_sql}"
        )
        source_ddl_before: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.orders_existing"
            ).result_rows[0][0]
        )
        exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=("orders_enriched",),
            start_time="2026-07-28T00:00:02Z",
        )
        build_error: str = capsys.readouterr().err
        source_ddl_after: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.orders_existing"
            ).result_rows[0][0]
        )
        source_row_count: int = int(
            clickhouse_client.query(
                f"SELECT count() FROM {clickhouse_database}.orders_existing"
            ).result_rows[0][0]
        )
        target_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
        coverage_ranges: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
    finally:
        connection.close()

    assert (exit_code, build_error) == (0, "")
    assert source_ddl_after == source_ddl_before
    assert source_row_count == 3
    assert target_rows == test_case.expected_order_ids
    assert coverage_ranges == test_case.expected_coverage


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectManualWorkflowIntegrationTestCase(
            description="command numbered steps and combined workflow converge identically",
            expected_exit_code=0,
            expected_order_ids=("order-1", "order-2"),
            expected_owned_relations=("mv__orders_enriched", "tbl__orders_enriched"),
            expected_replay_coverage_ranges=(("_replay_partition=0", "1", "2"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_published_direct_workflows_when_executing_manually_then_they_match_command(
    test_case: CliDirectManualWorkflowIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    numbered_database: str = f"{clickhouse_database}_steps"
    combined_database: str = f"{clickhouse_database}_combined"
    databases: tuple[str, ...] = (clickhouse_database, numbered_database, combined_database)
    write_direct_adopted_source_project(
        project_root=tmp_path,
        source_yml=_ADOPTED_SOURCE_TEST_CASES[0].source_yml,
        model_sql=_ADOPTED_SOURCE_TEST_CASES[0].model_sql,
    )
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    try:
        clickhouse_client.command(f"CREATE DATABASE {numbered_database}")
        clickhouse_client.command(f"CREATE DATABASE {combined_database}")
        database: str
        for database in databases:
            clickhouse_client.command(
                f"CREATE TABLE {database}.orders_existing "
                "(order_id String, event_partition Int32, event_offset Int64, "
                "event_timestamp DateTime64(3)) ENGINE = MergeTree ORDER BY order_id"
            )
            clickhouse_client.command(
                f"INSERT INTO {database}.orders_existing VALUES "
                "('order-1', 0, 1, '2026-07-28 00:00:01.000'), "
                "('order-2', 0, 2, '2026-07-28 00:00:02.000')"
            )
        command_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
        )
        _ = capsys.readouterr()
        numbered: PublishedBuildWorkflow = publish_direct_workflow(
            project_root=tmp_path,
            database=numbered_database,
            connection=connection,
        )
        step_sql: tuple[str, ...] = tuple(
            path.read_text(encoding="utf-8")
            for path in sorted((numbered.artifact_root / "steps").iterdir())
        )
        step_results: tuple[tuple[int, str], ...] = tuple(
            execute_clickhouse_client_sql(settings=clickhouse_connection_settings, sql=sql)
            for sql in step_sql
        )
        combined: PublishedBuildWorkflow = publish_direct_workflow(
            project_root=tmp_path,
            database=combined_database,
            connection=connection,
        )
        combined_sql: str = (combined.artifact_root / "workflow.sql").read_text(encoding="utf-8")
        combined_result: tuple[int, str] = execute_clickhouse_client_sql(
            settings=clickhouse_connection_settings,
            sql=combined_sql,
        )
        order_ids: tuple[tuple[str, ...], ...] = tuple(
            direct_build_order_ids(clickhouse_client=clickhouse_client, database=database)
            for database in databases
        )
        ownership_names: tuple[tuple[str, ...], ...] = tuple(
            direct_owned_relation_names(connection=connection, database=database)
            for database in databases
        )
        coverage_ranges: tuple[tuple[tuple[str, str, str], ...], ...] = tuple(
            direct_owned_replay_coverage_ranges(connection=connection, database=database)
            for database in databases
        )
    finally:
        clickhouse_client.command(f"DROP DATABASE IF EXISTS {numbered_database} SYNC")
        clickhouse_client.command(f"DROP DATABASE IF EXISTS {combined_database} SYNC")
        connection.close()

    assert command_exit_code == test_case.expected_exit_code
    assert tuple(result[0] for result in step_results) == tuple(
        test_case.expected_exit_code for _result in step_results
    )
    assert combined_result[0] == test_case.expected_exit_code
    assert combined_sql == "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((combined.artifact_root / "steps").iterdir())
    )
    assert order_ids == tuple(test_case.expected_order_ids for _database in databases)
    assert ownership_names == tuple(test_case.expected_owned_relations for _database in databases)
    assert coverage_ranges == tuple(
        test_case.expected_replay_coverage_ranges for _database in databases
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectLandedAtClockIntegrationTestCase(
            description="replays server-stamped landed-at rows with an implicit warehouse cutoff",
            landing_rows=(("landed-1", 0, 1), ("landed-2", 0, 2)),
            expected_order_ids=("landed-1", "landed-2"),
            expected_warehouse_written_rows=(2,),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_server_stamped_landed_at_rows_when_direct_building_then_client_clock_is_irrelevant(
    test_case: CliDirectLandedAtClockIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path, replay_boundary_mode="landed_at")
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        first_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        second_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        second_payload: dict[str, object] = json.loads(capsys.readouterr().out)
        replay_payloads: list[dict[str, object]] = cast(
            list[dict[str, object]], second_payload["replays"]
        )
        order_ids: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
    finally:
        connection.close()

    assert (first_exit_code, second_exit_code) == (0, 0)
    assert order_ids == test_case.expected_order_ids
    assert tuple(payload["warehouse_written_rows"] for payload in replay_payloads) == (
        test_case.expected_warehouse_written_rows
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectRelationRenameIntegrationTestCase(
            description="direct relation rename removes prior owned table and claim",
            initial_relation_name="orders_before_rename",
            renamed_relation_name="orders_after_rename",
            expected_rows=("order-1", "order-2"),
            expected_owned_relations=("mv__orders_enriched", "orders_after_rename"),
            expected_dropped_relations=(
                "mv__orders_enriched",
                "orders_after_rename",
                "orders_before_rename",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_owned_model_when_relation_name_changes_then_old_relation_is_retired(
    test_case: CliDirectRelationRenameIntegrationTestCase,
    tmp_path: Path,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(
        project_root=tmp_path,
        relation_name=test_case.initial_relation_name,
    )
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = execute_direct_build_directly(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            stabilization_seconds=0,
            selectors=(),
        )
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        _ = execute_direct_build_directly(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            stabilization_seconds=0,
            selectors=(),
        )
        write_direct_build_project(
            project_root=tmp_path,
            relation_name=test_case.renamed_relation_name,
        )
        result: DirectBuildResult = execute_direct_build_directly(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            stabilization_seconds=0,
            selectors=(),
        )
        renamed_rows: tuple[str, ...] = direct_relation_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            relation_name=test_case.renamed_relation_name,
        )
        catalog_relation_names: frozenset[str] = connection.load_catalog(
            clickhouse_database
        ).relation_names()
        owned_relation_names: tuple[str, ...] = direct_owned_relation_names(
            connection=connection,
            database=clickhouse_database,
        )
        materialized_view_target: str | None = cast(
            CatalogRelation,
            connection.load_catalog(clickhouse_database).relation("mv__orders_enriched"),
        ).target_relation_name
    finally:
        connection.close()

    assert renamed_rows == test_case.expected_rows
    assert result.dropped_relation_names == test_case.expected_dropped_relations
    assert owned_relation_names == test_case.expected_owned_relations
    assert test_case.initial_relation_name not in catalog_relation_names
    assert materialized_view_target == test_case.renamed_relation_name


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectViewBuildIntegrationTestCase(
            description="selected multi-upstream view builds and reruns without replay state",
            selectors=("customer_orders",),
            expected_rows=(("order-1", "Ada"), ("order-2", "Grace")),
            expected_relation_name="customer_orders",
            expected_resource_kind="view",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multi_upstream_view_when_building_direct_then_it_is_queryable_and_owned(
    test_case: CliDirectViewBuildIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_view_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.direct_orders_input "
            "(order_id String, customer_id UInt64, event_timestamp DateTime64(3)) "
            "ENGINE = MergeTree ORDER BY order_id"
        )
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.direct_customers_input "
            "(customer_id UInt64, customer_name String, event_timestamp DateTime64(3)) "
            "ENGINE = MergeTree ORDER BY customer_id"
        )
        clickhouse_client.command(
            f"INSERT INTO {clickhouse_database}.direct_orders_input VALUES "
            "('order-1', 1, now64(3)), ('order-2', 2, now64(3))"
        )
        clickhouse_client.command(
            f"INSERT INTO {clickhouse_database}.direct_customers_input VALUES "
            "(1, 'Ada', now64(3)), (2, 'Grace', now64(3))"
        )
        first_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        _ = capsys.readouterr()
        result: DirectBuildResult = execute_direct_build_directly(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            stabilization_seconds=0,
            selectors=test_case.selectors,
        )
        rows: tuple[tuple[str, str], ...] = tuple(
            (str(row[0]), str(row[1]))
            for row in clickhouse_client.query(
                f"SELECT order_id, customer_name FROM {clickhouse_database}.customer_orders "
                "ORDER BY order_id"
            ).result_rows
        )
        ownership_rows: tuple[tuple[object, ...], ...] = tuple(
            (record.relation_name, record.resource_kind)
            for record in connection.load_target_ownership(clickhouse_database)
        )
    finally:
        connection.close()

    assert first_exit_code == 0
    assert rows == test_case.expected_rows
    assert ownership_rows == ((test_case.expected_relation_name, test_case.expected_resource_kind),)
    assert result.replay_results == ()
    assert result.boundaries == ()
    assert result.ownership_records[0].replay_coverage == ()


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectBuildBoundaryIntegrationTestCase(
            description="a freshly created target yields one inclusive preserved cutoff",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            pre_capture_statements=("TRUNCATE TABLE {database}.tbl__orders_enriched",),
            expected_boundary_keys=("_replay_partition=0",),
            expected_cutoff_values=("2",),
            expected_cutoff_inclusive=(True,),
        ),
        CliDirectBuildBoundaryIntegrationTestCase(
            description="live rows already in the target still use the inclusive source cutoff",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            pre_capture_statements=(),
            expected_boundary_keys=("_replay_partition=0",),
            expected_cutoff_values=("2",),
            expected_cutoff_inclusive=(True,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_different_target_states_when_rebuilding_then_inclusive_source_contract_is_used(
    test_case: CliDirectBuildBoundaryIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        execute_warehouse_statements(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            statements=test_case.pre_capture_statements,
        )
        result: DirectBuildResult = execute_direct_build_directly(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            stabilization_seconds=0,
            selectors=(),
        )
        boundaries: tuple[DirectReplayBoundary, ...] = result.boundaries
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
        CliDirectBuildGuardIntegrationTestCase(
            description="managed Kafka drift blocks the build before any model teardown",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            rebuilt_topic="source.orders.renamed",
            pre_rebuild_statements=(),
            expected_exit_code=1,
            expected_error_fragment="Direct build preserves managed source infrastructure",
            expected_order_ids=("order-1", "order-2"),
        ),
        CliDirectBuildGuardIntegrationTestCase(
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
        CliDirectBuildGuardIntegrationTestCase(
            description="an aged-out driving input blocks the rerun with explicit guidance",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            rebuilt_topic="source.orders",
            pre_rebuild_statements=(
                "ALTER TABLE {database}.raw__orders DELETE WHERE _replay_offset <= 1 "
                "SETTINGS mutations_sync = 2",
            ),
            expected_exit_code=1,
            expected_error_fragment=(
                "Direct rerun would silently drop retained history because the preserved "
                "driving input no longer covers the required replay range"
            ),
            expected_order_ids=("order-1", "order-2"),
        ),
        CliDirectBuildGuardIntegrationTestCase(
            description="a target without its ownership record blocks the build as unmanaged",
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            rebuilt_topic="source.orders",
            pre_rebuild_statements=("TRUNCATE TABLE {database}._streambuild_direct_target_events",),
            expected_exit_code=1,
            expected_error_fragment="Direct mode refuses to replace relations it does not own",
            expected_order_ids=("order-1", "order-2"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_warehouse_state_when_building_then_it_blocks_before_teardown(
    test_case: CliDirectBuildGuardIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        execute_warehouse_statements(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            statements=test_case.pre_rebuild_statements,
        )
        write_direct_build_project(project_root=tmp_path, topic=test_case.rebuilt_topic)
        exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        command_error: str = capsys.readouterr().err
        order_ids: tuple[str, ...] = direct_build_order_ids(
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
            description="virtual build refuses a direct-owned target",
            expected_exit_code=1,
            expected_error_fragment=(
                "Virtual environments refuse to take over relations owned by direct mode"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_owned_targets_when_building_virtual_then_virtual_environments_are_rejected(
    test_case: CliReciprocalOwnershipIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        build_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        write_direct_build_project(project_root=tmp_path, virtual_environments=True)
        virtual_build_exit_code: int = run_virtual_environment_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        virtual_build_error: str = capsys.readouterr().err
    finally:
        connection.close()

    assert build_exit_code == 0
    assert virtual_build_exit_code == test_case.expected_exit_code
    assert test_case.expected_error_fragment in virtual_build_error


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliReciprocalOwnershipIntegrationTestCase(
            description="direct build refuses a virtual-environment target",
            expected_exit_code=1,
            expected_error_fragment="Direct mode refuses to replace relations it does not own",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_environment_target_when_building_direct_then_it_is_rejected(
    test_case: CliReciprocalOwnershipIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path, virtual_environments=True)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        virtual_build_exit_code: int = run_virtual_environment_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        write_direct_build_project(project_root=tmp_path)
        build_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        build_error: str = capsys.readouterr().err
    finally:
        connection.close()

    assert virtual_build_exit_code == 0
    assert build_exit_code == test_case.expected_exit_code
    assert test_case.expected_error_fragment in build_error


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectBuildAuditIntegrationTestCase(
            description="a failing audit fails the command while the built rows remain live",
            audit_sql_by_name=(
                (
                    "broken_column.sql",
                    'AUDIT (\n  description: "warehouse errors are recorded",\n);\n\n'
                    'SELECT missing_order_id\nFROM __ref("orders_enriched")\n',
                ),
                (
                    "first_nonempty_order_ids.sql",
                    'AUDIT (\n  description: "order ids must not be empty",\n);\n\n'
                    'SELECT order_id\nFROM __ref("orders_enriched")\n'
                    "WHERE order_id != '' ORDER BY order_id\n",
                ),
                (
                    "second_nonempty_order_ids.sql",
                    'AUDIT (\n  description: "all order ids fail again",\n);\n\n'
                    'SELECT order_id\nFROM __ref("orders_enriched")\n'
                    "WHERE order_id != '' ORDER BY order_id\n",
                ),
            ),
            landing_rows=(
                ("order-1", 0, 1),
                ("order-2", 0, 2),
                ("order-3", 0, 3),
                ("order-4", 0, 4),
                ("order-5", 0, 5),
                ("order-6", 0, 6),
            ),
            late_landing_rows=(("order-7", 0, 7),),
            expected_exit_code=1,
            expected_stdout_fragment="FAIL",
            expected_final_order_ids=(
                "order-1",
                "order-2",
                "order-3",
                "order-4",
                "order-5",
                "order-6",
                "order-7",
            ),
            expected_audit_observation_rows=(
                (
                    "error",
                    1,
                    '{"sample_column_names":[],"sample_rows":[]}',
                ),
                (
                    "failed",
                    6,
                    '{"sample_column_names":["order_id"],"sample_rows":'
                    '[["order-1"],["order-2"],["order-3"],["order-4"],["order-5"]]}',
                ),
                (
                    "failed",
                    6,
                    '{"sample_column_names":["order_id"],"sample_rows":'
                    '[["order-1"],["order-2"],["order-3"],["order-4"],["order-5"]]}',
                ),
            ),
            expected_final_coverage=(("_replay_partition=0", "1", "6"),),
            expected_sample_query_fragment="AS __streambuild_audit LIMIT 5;",
            expected_error_message_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_audit_when_building_then_command_fails_without_rollback(
    test_case: CliDirectBuildAuditIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        clickhouse_client.command(f"TRUNCATE TABLE {clickhouse_database}.tbl__orders_enriched")
        write_direct_build_project(
            project_root=tmp_path, audit_sql_by_name=test_case.audit_sql_by_name
        )
        exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            json_output=False,
        )
        command_output: str = capsys.readouterr().out
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.late_landing_rows,
        )
        final_order_ids: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
        build_observation_rows: Sequence[Sequence[object]] = clickhouse_client.query(
            "SELECT outcome, materialized_outcome FROM "
            f"{clickhouse_database}._streambuild_invocations "
            "WHERE command = 'build' ORDER BY completed_at DESC LIMIT 1"
        ).result_rows
        audit_observation_rows: Sequence[Sequence[object]] = clickhouse_client.query(
            "SELECT status, failure_count, payload_json FROM "
            f"{clickhouse_database}._streambuild_node_results "
            "WHERE node_kind = 'audit' AND invocation_id = ("
            "SELECT invocation_id FROM "
            f"{clickhouse_database}._streambuild_invocations WHERE command = 'build' "
            "ORDER BY completed_at DESC LIMIT 1) ORDER BY node_identity"
        ).result_rows
        audit_error_message_count: int = int(
            clickhouse_client.query(
                f"SELECT count() FROM {clickhouse_database}._streambuild_node_results "
                "WHERE node_kind = 'audit' AND error_message IS NOT NULL AND invocation_id = ("
                "SELECT invocation_id FROM "
                f"{clickhouse_database}._streambuild_invocations WHERE command = 'build' "
                "ORDER BY completed_at DESC LIMIT 1)"
            ).result_rows[0][0]
        )
        final_coverage: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
        workflow_sql: str = (tmp_path / "target" / "run" / "build" / "workflow.sql").read_text(
            encoding="utf-8"
        )
    finally:
        connection.close()

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stdout_fragment in command_output
    assert final_order_ids == test_case.expected_final_order_ids
    assert build_observation_rows == [("failed", "applied")]
    assert tuple(audit_observation_rows) == test_case.expected_audit_observation_rows
    assert final_coverage == test_case.expected_final_coverage
    assert workflow_sql.count(test_case.expected_sample_query_fragment) == len(
        test_case.audit_sql_by_name
    )
    assert audit_error_message_count == test_case.expected_error_message_count


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectBuildRerunIntegrationTestCase(
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
    test_case: CliDirectBuildRerunIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        connection: AdapterConnection = FailOnceRealizationConnection(delegate)
        failed_exit_code: int = run_direct_build(
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
        clickhouse_client.command(
            f"ALTER TABLE {clickhouse_database}.raw__orders DELETE WHERE _replay_offset <= 1 "
            "SETTINGS mutations_sync = 2"
        )
        retention_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        retention_error: str = capsys.readouterr().err
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.restored_landing_rows,
        )
        rerun_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.late_landing_rows,
        )
        final_order_ids: tuple[str, ...] = direct_build_order_ids(
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
        CliDirectBuildPartialFailureIntegrationTestCase(
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
    test_case: CliDirectBuildPartialFailureIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        _ = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        connection: AdapterConnection = FailOnceReplayConnection(delegate)
        failed_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.partial_landing_rows,
        )
        clickhouse_client.command(
            f"ALTER TABLE {clickhouse_database}.raw__orders DELETE WHERE _replay_offset <= 1 "
            "SETTINGS mutations_sync = 2"
        )
        retention_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        retention_error: str = capsys.readouterr().err
        partial_order_ids: tuple[str, ...] = direct_build_order_ids(
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
        CliDirectSelectedBuildIntegrationTestCase(
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
                "mv__beta",
                "tbl__gamma",
                "tbl__delta",
                "mv__delta",
                "mv__gamma",
            ),
            expected_replay_targets=("tbl__beta", "tbl__delta"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_settled_graph_when_building_selected_model_then_closure_rebuilds_once(
    test_case: CliDirectSelectedBuildIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        prerequisite_before: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="alpha",
        )
        connection: DirectActionRecordingConnection = DirectActionRecordingConnection(delegate)
        with ThreadPoolExecutor(max_workers=1) as executor:
            boundary_future: Future[None] = executor.submit(
                insert_landing_rows_after_delay,
                connection_settings=clickhouse_connection_settings,
                database=clickhouse_database,
                rows=test_case.boundary_landing_rows,
                delay_seconds=0.2,
            )
            _ = execute_direct_build_directly(
                project_root=tmp_path,
                database=clickhouse_database,
                connection=connection,
                stabilization_seconds=1.0,
                selectors=test_case.selectors,
            )
            _ = boundary_future.result()
        repeated_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        _ = capsys.readouterr()
        prerequisite_after: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="alpha",
        )
        beta_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
        gamma_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="gamma",
        )
        delta_rows: tuple[tuple[str, str], ...] = direct_graph_delta_rows(
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
        CliDirectAggregateBuildIntegrationTestCase(
            description="aggregate root rebuilds through the shared replay path",
            selectors=("beta",),
            landing_rows=(("order-1", 0, 1), ("order-2", 0, 2)),
            expected_aggregate_rows=(
                ("order-1", 2),
                ("order-2", 2),
            ),
            expected_replay_targets=("tbl__beta",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_aggregate_root_when_building_selected_model_then_it_uses_shared_replay(
    test_case: CliDirectAggregateBuildIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_aggregate_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        connection: ManagedLiveInsertConnection = ManagedLiveInsertConnection(
            delegate,
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        aggregate_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        aggregate_error: str = capsys.readouterr().err
        aggregate_rows: tuple[tuple[str, int], ...] = tuple(
            (str(row[0]), int(row[1]))
            for row in clickhouse_client.query(
                f"SELECT order_id, sum(order_count) FROM {clickhouse_database}.tbl__beta "
                "GROUP BY order_id "
                "ORDER BY order_id"
            ).result_rows
        )
    finally:
        delegate.close()

    assert aggregate_error == ""
    assert (initial_exit_code, aggregate_exit_code) == (0, 0)
    assert aggregate_rows == test_case.expected_aggregate_rows
    assert tuple(connection.replay_targets) == test_case.expected_replay_targets
    assert "tbl__beta" in connection.realized_relation_names
    assert "mv__beta" in connection.realized_relation_names


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectSelectedFailureIntegrationTestCase(
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
                "tbl__delta",
                "tbl__beta",
                "tbl__delta",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_selected_population_when_retrying_then_closure_reconstructs_exactly(
    test_case: CliDirectSelectedFailureIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=test_case.landing_rows,
        )
        connection: FailSecondReplayOnceConnection = FailSecondReplayOnceConnection(delegate)
        failed_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        failure_error: str = capsys.readouterr().err
        rerun_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        rerun_error: str = capsys.readouterr().err
        beta_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
        gamma_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="gamma",
        )
        delta_rows: tuple[tuple[str, str], ...] = direct_graph_delta_rows(
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
        CliDirectExecutionStepFailureIntegrationTestCase(
            description="teardown failure is safe to retry",
            connection_factory=FailOnceDropConnection,
            expected_failure_fragment="injected failure during selected teardown",
            expected_failed_invocation_count=1,
            expected_failed_mode="direct",
            expected_min_selected_node_count=1,
        ),
        CliDirectExecutionStepFailureIntegrationTestCase(
            description="view attachment failure is safe to retry",
            connection_factory=FailOnceViewRealizationConnection,
            expected_failure_fragment="injected failure during selected view attachment",
            expected_failed_invocation_count=1,
            expected_failed_mode="direct",
            expected_min_selected_node_count=1,
        ),
        CliDirectExecutionStepFailureIntegrationTestCase(
            description="boundary capture failure is safe to retry",
            connection_factory=FailOnceBoundaryQueryConnection,
            expected_failure_fragment="injected failure during selected boundary capture",
            expected_failed_invocation_count=1,
            expected_failed_mode="direct",
            expected_min_selected_node_count=1,
        ),
        CliDirectExecutionStepFailureIntegrationTestCase(
            description="final ownership failure is safe to retry",
            connection_factory=FailFinalOwnershipOnceConnection,
            expected_failure_fragment="injected failure during final ownership persistence",
            expected_failed_invocation_count=1,
            expected_failed_mode="direct",
            expected_min_selected_node_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selected_execution_step_failure_when_retrying_then_result_is_exact(
    test_case: CliDirectExecutionStepFailureIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        connection: AdapterConnection = test_case.connection_factory(delegate)
        failed_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=("beta",),
        )
        failure_error: str = capsys.readouterr().err
        failed_invocation_count: int = int(
            clickhouse_client.query(
                f"SELECT count() FROM {clickhouse_database}._streambuild_invocations "
                "WHERE command = 'build' AND outcome = 'failed'"
            ).result_rows[0][0]
        )
        failed_invocation_context: Sequence[Sequence[object]] = clickhouse_client.query(
            f"SELECT mode, selected_node_count FROM "
            f"{clickhouse_database}._streambuild_invocations "
            "WHERE command = 'build' AND outcome = 'failed' LIMIT 1"
        ).result_rows
        rerun_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=("beta",),
        )
        rerun_error: str = capsys.readouterr().err
        beta_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
        gamma_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="gamma",
        )
        delta_rows: tuple[tuple[str, str], ...] = direct_graph_delta_rows(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
    finally:
        delegate.close()

    assert (initial_exit_code, failed_exit_code, rerun_exit_code) == (0, 1, 0)
    assert test_case.expected_failure_fragment in failure_error
    assert failed_invocation_count == test_case.expected_failed_invocation_count
    assert failed_invocation_context[0][0] == test_case.expected_failed_mode
    assert int(failed_invocation_context[0][1]) >= test_case.expected_min_selected_node_count
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
        CliDirectSelectionMatrixIntegrationTestCase(
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
            expected_replay_targets=("tbl__alpha", "tbl__delta"),
        ),
        CliDirectSelectionMatrixIntegrationTestCase(
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
        CliDirectSelectionMatrixIntegrationTestCase(
            description="leaf selection rebuilds only the leaf",
            selectors=("delta",),
            expected_drop_relation_names=("mv__delta", "tbl__delta"),
            expected_replay_targets=("tbl__delta",),
        ),
        CliDirectSelectionMatrixIntegrationTestCase(
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
    test_case: CliDirectSelectionMatrixIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        connection: DirectActionRecordingConnection = DirectActionRecordingConnection(delegate)
        selected_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        selected_error: str = capsys.readouterr().err
        alpha_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="alpha",
        )
        beta_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="beta",
        )
        gamma_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="gamma",
        )
        delta_rows: tuple[tuple[str, str], ...] = direct_graph_delta_rows(
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
        CliDirectSelectedAuditIntegrationTestCase(
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
    test_case: CliDirectSelectedAuditIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_selected_graph_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path, database=clickhouse_database, connection=delegate
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1),),
        )
        write_direct_selected_graph_audits(
            project_root=tmp_path, audit_sql_by_name=test_case.audit_sql_by_name
        )
        connection: DirectActionRecordingConnection = DirectActionRecordingConnection(delegate)
        selected_exit_code: int = run_direct_build(
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


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectAdoptedSourceIntegrationTestCase(
            description=case.description,
            source_yml=case.source_yml,
            model_sql=case.model_sql,
            source_columns_sql=case.source_columns_sql,
            initial_values_sql=case.initial_values_sql,
            live_values_sql=case.live_values_sql,
            source_projection_sql=case.source_projection_sql,
            expected_source_rows=case.expected_source_rows,
            expected_order_ids=case.expected_order_ids,
            expected_replay_mode=case.expected_replay_mode,
            expected_replay_columns=case.expected_replay_columns,
        )
        for case in _ADOPTED_SOURCE_TEST_CASES
    ],
    ids=lambda case: case.description,
)
def test_given_adopted_source_when_building_direct_then_source_is_preserved_and_rows_are_exact(
    test_case: CliDirectAdoptedSourceIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_adopted_source_project(
        project_root=tmp_path,
        source_yml=test_case.source_yml,
        model_sql=test_case.model_sql,
    )
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.orders_existing "
            f"({test_case.source_columns_sql}) ENGINE = MergeTree() ORDER BY order_id"
        )
        clickhouse_client.command(
            f"INSERT INTO {clickhouse_database}.orders_existing VALUES "
            f"{test_case.initial_values_sql}"
        )
        source_ddl_before: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.orders_existing"
            ).result_rows[0][0]
        )
        connection: AdoptedLiveInsertConnection = AdoptedLiveInsertConnection(
            delegate,
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            values_sql=test_case.live_values_sql,
        )
        build_result: DirectBuildResult = execute_direct_build_directly(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            stabilization_seconds=0,
            selectors=(),
        )
        rerun_connection: DirectActionRecordingConnection = DirectActionRecordingConnection(
            delegate
        )
        rerun_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=rerun_connection,
            selectors=(),
        )
        _ = capsys.readouterr()
        source_ddl_after: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.orders_existing"
            ).result_rows[0][0]
        )
        source_rows: tuple[tuple[str, ...], ...] = stringify_warehouse_rows(
            rows=clickhouse_client.query(
                f"SELECT {test_case.source_projection_sql} FROM "
                f"{clickhouse_database}.orders_existing ORDER BY order_id"
            ).result_rows,
        )
        target_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client, database=clickhouse_database
        )
        ownership_names: tuple[str, ...] = direct_owned_relation_names(
            connection=connection, database=clickhouse_database
        )
    finally:
        delegate.close()

    replay_request: AdapterReplayRequest = connection.replay_requests[0]
    assert source_ddl_after == source_ddl_before
    assert rerun_exit_code == 0
    assert source_rows == test_case.expected_source_rows
    assert target_rows == test_case.expected_order_ids
    assert str(replay_request.mode) == test_case.expected_replay_mode
    assert (
        replay_request.columns.partition,
        replay_request.columns.offset,
        replay_request.columns.timestamp,
        replay_request.columns.landed_at,
        replay_request.columns.cursor,
    ) == test_case.expected_replay_columns
    assert tuple(boundary.cutoff_inclusive for boundary in build_result.boundaries) == (True,)
    assert "orders_existing" not in ownership_names
    assert not any("orders_existing" in statement for statement in connection.command_statements)
    assert not any(
        "orders_existing" in statement for statement in rerun_connection.command_statements
    )
    assert "adopted-audit-marker" in "\n".join(rerun_connection.query_statements)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectAdoptedSourceFailureIntegrationTestCase(
            description="missing adopted mapping column rejects before teardown",
            source_table_name="orders_existing",
            source_yml=_ADOPTED_SOURCE_TEST_CASES[0].source_yml,
            model_sql=_ADOPTED_SOURCE_TEST_CASES[0].model_sql,
            source_columns_sql=(
                "order_id String, event_partition Int32, event_timestamp DateTime64(3)"
            ),
            expected_error_fragment="is missing declared offset column 'event_offset'",
        ),
        CliDirectAdoptedSourceFailureIntegrationTestCase(
            description="injected replay alias collision rejects before teardown",
            source_table_name="orders_existing",
            source_yml=_ADOPTED_SOURCE_TEST_CASES[0].source_yml,
            model_sql=_ADOPTED_SOURCE_TEST_CASES[0].model_sql,
            source_columns_sql=(
                "order_id String, event_partition Int32, event_offset Int64, "
                "event_timestamp DateTime64(3), _replay_offset Int64"
            ),
            expected_error_fragment="conflicts with the injected replay alias",
        ),
        CliDirectAdoptedSourceFailureIntegrationTestCase(
            description="adopted source target collision rejects before teardown",
            source_table_name="tbl__orders_enriched",
            source_yml=(
                "sources:\n"
                "  - kind: stream_table\n"
                "    name: orders\n"
                "    table_name: tbl__orders_enriched\n"
                "    replay_boundary:\n"
                "      mode: offsets\n"
                "      columns:\n"
                "        _replay_partition: event_partition\n"
                "        _replay_offset: event_offset\n"
                "        _replay_timestamp: event_timestamp\n"
            ),
            model_sql=_ADOPTED_SOURCE_TEST_CASES[0].model_sql,
            source_columns_sql=(
                "order_id String, event_partition Int32, event_offset Int64, "
                "event_timestamp DateTime64(3)"
            ),
            expected_error_fragment=(
                "Relation name 'tbl__orders_enriched' is used by both model "
                "'orders_enriched' and adopted source 'orders'"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_adopted_source_when_building_then_it_rejects_before_destructive_work(
    test_case: CliDirectAdoptedSourceFailureIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_adopted_source_project(
        project_root=tmp_path,
        source_yml=test_case.source_yml,
        model_sql=test_case.model_sql,
    )
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.{test_case.source_table_name} "
            f"({test_case.source_columns_sql}) ENGINE = MergeTree() ORDER BY order_id"
        )
        source_ddl_before: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.{test_case.source_table_name}"
            ).result_rows[0][0]
        )
        connection: DirectActionRecordingConnection = DirectActionRecordingConnection(delegate)
        exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
        )
        build_error: str = capsys.readouterr().err
        source_ddl_after: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.{test_case.source_table_name}"
            ).result_rows[0][0]
        )
    finally:
        delegate.close()

    assert exit_code == 1
    assert test_case.expected_error_fragment in build_error
    assert source_ddl_after == source_ddl_before
    assert connection.command_statements == []
    assert connection.realized_relation_names == []
    assert connection.replay_targets == []


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectStartTimeIntegrationTestCase(
            description="offset replay keeps the inclusive frontier and supersedes prior coverage",
            selectors=("orders_enriched",),
            expected_source_rows=(
                ("order-1", 1),
                ("order-2", 2),
                ("order-3", 3),
                ("order-4", 4),
            ),
            expected_target_rows=("order-2", "order-3", "order-4"),
            expected_coverage=(("_replay_partition=0", "2", "4"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_offset_when_building_from_start_time_then_replay_is_unseeded_and_bounded(
    test_case: CliDirectStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        requested_start_time: str = connection.capture_warehouse_timestamp().replace(" ", "T") + "Z"
        effective_start_time: str = requested_start_time.replace("T", " ").removesuffix("Z")
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-3", 0, 3), ("order-4", 0, 4)),
        )
        source_ddl_before: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.raw__orders"
            ).result_rows[0][0]
        )
        plan_exit_code: int = run_direct_plan(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=requested_start_time,
        )
        plan_capture: CaptureResult[str] = capsys.readouterr()
        plan_artifact: tuple[bytes, bytes, tuple[str, ...], tuple[bytes, ...]] = (
            read_workflow_artifact(artifact_root=tmp_path / "target/run/plan")
        )
        pipeline_plan_exit_code: int = run_direct_plan(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=("pipeline:orders",),
            start_time=requested_start_time,
        )
        pipeline_plan_capture: CaptureResult[str] = capsys.readouterr()
        pipeline_plan_artifact: tuple[bytes, bytes, tuple[str, ...], tuple[bytes, ...]] = (
            read_workflow_artifact(artifact_root=tmp_path / "target/run/plan")
        )
        bounded_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=requested_start_time,
        )
        bounded_error: str = capsys.readouterr().err
        source_ddl_after: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.raw__orders"
            ).result_rows[0][0]
        )
        source_rows: tuple[tuple[str, int], ...] = tuple(
            (str(row[0]), int(row[1]))
            for row in clickhouse_client.query(
                f"SELECT kafka_key, kafka_offset FROM {clickhouse_database}.raw__orders "
                "ORDER BY kafka_offset"
            ).result_rows
        )
        bounded_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
        coverage_ranges: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
        plan_payload: dict[str, object] = json.loads(
            (tmp_path / "target/run/build/plan.json").read_text(encoding="utf-8")
        )
        workflow_sql: str = (tmp_path / "target/run/build/workflow.sql").read_text(encoding="utf-8")
        build_artifact: tuple[bytes, bytes, tuple[str, ...], tuple[bytes, ...]] = (
            read_workflow_artifact(artifact_root=tmp_path / "target/run/build")
        )
    finally:
        connection.close()

    assert (initial_exit_code, plan_exit_code, plan_capture.err) == (0, 0, "")
    assert (pipeline_plan_exit_code, pipeline_plan_capture.err) == (0, "")
    assert plan_capture.out.encode("utf-8") == plan_artifact[0]
    assert pipeline_plan_capture.out == plan_capture.out
    assert pipeline_plan_artifact == plan_artifact
    assert plan_artifact == build_artifact
    assert bounded_exit_code == 0, bounded_error
    assert source_ddl_after == source_ddl_before
    assert source_rows == test_case.expected_source_rows
    assert bounded_rows == test_case.expected_target_rows
    assert coverage_ranges == test_case.expected_coverage
    assert plan_payload["start_time"] == effective_start_time
    assert effective_start_time in workflow_sql
    assert "INSERT INTO" in workflow_sql
    assert "active_start_offsets" in workflow_sql


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectLandedAtStartTimeIntegrationTestCase(
            description="landed-at replay uses the inclusive physical source clock",
            expected_target_rows=("order-3", "order-4"),
            expected_boundary_keys=("_replay_landed_at",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_landed_at_source_when_building_from_start_time_then_rows_are_bounded(
    test_case: CliDirectLandedAtStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path, replay_boundary_mode="landed_at")
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        future_start_time: str = str(
            clickhouse_client.query(
                "SELECT toString(now64(3, 'UTC') + toIntervalMillisecond(200))"
            ).result_rows[0][0]
        )
        time.sleep(0.3)
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-3", 0, 3), ("order-4", 0, 4)),
        )
        bounded_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=("orders_enriched",),
            start_time=future_start_time.replace(" ", "T") + "Z",
        )
        bounded_error: str = capsys.readouterr().err
        target_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
        coverage_ranges: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
    finally:
        connection.close()

    assert (initial_exit_code, bounded_exit_code, bounded_error) == (0, 0, "")
    assert target_rows == test_case.expected_target_rows
    assert tuple(replay_range[0] for replay_range in coverage_ranges) == (
        test_case.expected_boundary_keys
    )
    assert len(coverage_ranges) == 1
    assert coverage_ranges[0][1] <= coverage_ranges[0][2]


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectStartTimeIntegrationTestCase(
            description="aggregate replay filters the physical source before grouping",
            selectors=("orders_enriched",),
            expected_source_rows=(
                ("order-1", 1),
                ("order-2", 2),
                ("order-3", 3),
                ("order-4", 4),
            ),
            expected_target_rows=("order-2", "order-3", "order-4"),
            expected_coverage=(("_replay_partition=0", "2", "4"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_aggregate_model_when_building_from_start_time_then_input_is_bounded(
    test_case: CliDirectStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    (tmp_path / "pipelines/orders/orders_enriched.sql").write_text(
        'MODEL (order_by ["order_id"]);\n'
        "SELECT kafka_key::String AS order_id, count()::UInt64 AS order_count "
        'FROM __source("orders") GROUP BY kafka_key\n',
        encoding="utf-8",
    )
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        requested_start_time: str = connection.capture_warehouse_timestamp().replace(" ", "T") + "Z"
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-3", 0, 3), ("order-4", 0, 4)),
        )
        bounded_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=requested_start_time,
        )
        bounded_error: str = capsys.readouterr().err
        target_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
        coverage_ranges: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
    finally:
        connection.close()

    assert (initial_exit_code, bounded_exit_code, bounded_error) == (0, 0, "")
    assert target_rows == test_case.expected_target_rows
    assert coverage_ranges == test_case.expected_coverage


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectStartTimeIntegrationTestCase(
            description="a missing interior offset fails before target teardown",
            selectors=("orders_enriched",),
            expected_source_rows=(("order-1", 1), ("order-2", 2), ("order-4", 4)),
            expected_target_rows=("order-1", "order-2", "order-3", "order-4"),
            expected_coverage=(("_replay_partition=0", "1", "4"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bounded_prior_range_with_gap_when_building_then_preflight_preserves_target(
    test_case: CliDirectStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        greenfield_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        requested_start_time: str = connection.capture_warehouse_timestamp().replace(" ", "T") + "Z"
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-3", 0, 3),),
        )
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-4", 0, 4),),
        )
        settled_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
        )
        _ = capsys.readouterr()
        target_ddl_before: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.tbl__orders_enriched"
            ).result_rows[0][0]
        )
        clickhouse_client.command(
            f"ALTER TABLE {clickhouse_database}.raw__orders DELETE WHERE _replay_offset = 3 "
            "SETTINGS mutations_sync = 2"
        )
        bounded_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=requested_start_time,
        )
        bounded_error: str = capsys.readouterr().err
        target_ddl_after: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.tbl__orders_enriched"
            ).result_rows[0][0]
        )
        source_rows: tuple[tuple[str, int], ...] = tuple(
            (str(row[0]), int(row[1]))
            for row in clickhouse_client.query(
                f"SELECT kafka_key, kafka_offset FROM {clickhouse_database}.raw__orders "
                "ORDER BY kafka_offset"
            ).result_rows
        )
        target_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
        coverage_ranges: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
    finally:
        connection.close()

    assert (greenfield_exit_code, settled_exit_code, bounded_exit_code) == (0, 0, 1)
    assert "no longer covers the required replay range" in bounded_error
    assert target_ddl_after == target_ddl_before
    assert source_rows == test_case.expected_source_rows
    assert target_rows == test_case.expected_target_rows
    assert coverage_ranges == test_case.expected_coverage


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectFutureSourceStartTimeIntegrationTestCase(
            description="future-dated rows beyond the captured cutoff fail before teardown",
            source_yml=_ADOPTED_SOURCE_TEST_CASES[1].source_yml,
            model_sql=_ADOPTED_SOURCE_TEST_CASES[1].model_sql,
            source_columns_sql=_ADOPTED_SOURCE_TEST_CASES[1].source_columns_sql,
            insert_sql=("SELECT 'order-future', now64(3, 'UTC') + toIntervalDay(1)"),
            start_time_sql="SELECT toString(now64(3, 'UTC'))",
            expected_target_count=0,
        ),
        CliDirectFutureSourceStartTimeIntegrationTestCase(
            description="cursor replay with no time-qualified frontier fails before teardown",
            source_yml=_ADOPTED_SOURCE_TEST_CASES[2].source_yml,
            model_sql=_ADOPTED_SOURCE_TEST_CASES[2].model_sql,
            source_columns_sql=_ADOPTED_SOURCE_TEST_CASES[2].source_columns_sql,
            insert_sql="SELECT 'order-past', toUInt64(1), now64(3, 'UTC')",
            start_time_sql=("SELECT toString(now64(3, 'UTC') + toIntervalDay(1))"),
            expected_target_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_without_qualified_bounded_input_when_building_then_preflight_fails(
    test_case: CliDirectFutureSourceStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_adopted_source_project(
        project_root=tmp_path,
        source_yml=test_case.source_yml,
        model_sql=test_case.model_sql,
    )
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.orders_existing "
            f"({test_case.source_columns_sql}) ENGINE = MergeTree() ORDER BY order_id"
        )
        clickhouse_client.command(
            f"INSERT INTO {clickhouse_database}.orders_existing {test_case.insert_sql}"
        )
        requested_start_time: str = (
            str(clickhouse_client.query(test_case.start_time_sql).result_rows[0][0]).replace(
                " ", "T"
            )
            + "Z"
        )
        source_ddl_before: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.orders_existing"
            ).result_rows[0][0]
        )
        exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=("orders_enriched",),
            start_time=requested_start_time,
        )
        build_error: str = capsys.readouterr().err
        source_ddl_after: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.orders_existing"
            ).result_rows[0][0]
        )
        target_count: int = int(
            clickhouse_client.query(
                "SELECT count() FROM system.tables "
                f"WHERE database = '{clickhouse_database}' AND name = 'tbl__orders_enriched'"
            ).result_rows[0][0]
        )
    finally:
        connection.close()

    assert exit_code == 1
    assert "has no qualifying input at or after the requested start time" in build_error
    assert source_ddl_after == source_ddl_before
    assert target_count == test_case.expected_target_count


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectStartTimeIntegrationTestCase(
            description="bounded greenfield build rejects an absent managed replay input",
            selectors=("orders_enriched",),
            expected_source_rows=(),
            expected_target_rows=(),
            expected_coverage=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_absent_managed_source_when_building_from_start_time_then_nothing_is_created(
    test_case: CliDirectStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time="2026-01-01T00:00:00Z",
        )
        build_error: str = capsys.readouterr().err
        created_names: tuple[str, ...] = tuple(
            str(row[0])
            for row in clickhouse_client.query(
                "SELECT name FROM system.tables "
                f"WHERE database = '{clickhouse_database}' "
                "AND name NOT LIKE '\\_streambuild%' ORDER BY name"
            ).result_rows
        )
    finally:
        connection.close()

    assert exit_code == 1
    assert "requires existing replay input 'raw__orders'" in build_error
    assert created_names == test_case.expected_target_rows


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectStartTimeIntegrationTestCase(
            description="bounded downstream root rejects missing intermediate time lineage",
            selectors=("alpha",),
            expected_source_rows=(),
            expected_target_rows=("order-1", "order-2"),
            expected_coverage=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_intermediate_without_time_lineage_when_building_then_target_is_preserved(
    test_case: CliDirectStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_selected_graph_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        initial_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        requested_start_time: str = connection.capture_warehouse_timestamp().replace(" ", "T") + "Z"
        target_ddl_before: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.tbl__alpha"
            ).result_rows[0][0]
        )
        bounded_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=requested_start_time,
        )
        build_error: str = capsys.readouterr().err
        target_ddl_after: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.tbl__alpha"
            ).result_rows[0][0]
        )
        target_rows: tuple[str, ...] = direct_graph_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            model_name="alpha",
        )
    finally:
        connection.close()

    assert (initial_exit_code, bounded_exit_code) == (0, 1)
    assert "does not expose time-lineage column '_replay_landed_at'" in build_error
    assert target_ddl_after == target_ddl_before
    assert target_rows == test_case.expected_target_rows


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectStartTimeIntegrationTestCase(
            description="bounded retries narrow and widen before ordinary replay restores history",
            selectors=("orders_enriched",),
            expected_source_rows=(
                ("order-1", 1),
                ("order-2", 2),
                ("order-3", 3),
                ("order-4", 4),
            ),
            expected_target_rows=("order-1", "order-2", "order-3", "order-4"),
            expected_coverage=(("_replay_partition=0", "1", "4"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bounded_failure_when_retrying_then_coverage_survives_narrows_and_widens(
    test_case: CliDirectStartTimeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_build_project(project_root=tmp_path)
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        greenfield_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=delegate,
        )
        _ = capsys.readouterr()
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-1", 0, 1), ("order-2", 0, 2)),
        )
        start_at_two: str = delegate.capture_warehouse_timestamp().replace(" ", "T") + "Z"
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-3", 0, 3),),
        )
        start_at_three: str = delegate.capture_warehouse_timestamp().replace(" ", "T") + "Z"
        insert_landing_rows(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            rows=(("order-4", 0, 4),),
        )
        settled_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=delegate,
        )
        _ = capsys.readouterr()
        connection: FailOnceDropConnection = FailOnceDropConnection(delegate)
        failed_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=start_at_two,
        )
        failed_error: str = capsys.readouterr().err
        failure_coverage: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
        retry_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=start_at_two,
        )
        retry_error: str = capsys.readouterr().err
        later_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=start_at_three,
        )
        later_error: str = capsys.readouterr().err
        later_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
        later_coverage: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
        earlier_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
            start_time=start_at_two,
        )
        earlier_error: str = capsys.readouterr().err
        earlier_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
        earlier_coverage: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
        ordinary_exit_code: int = run_direct_build(
            project_root=tmp_path,
            database=clickhouse_database,
            connection=connection,
            selectors=test_case.selectors,
        )
        ordinary_error: str = capsys.readouterr().err
        final_rows: tuple[str, ...] = direct_build_order_ids(
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
        )
        final_coverage: tuple[tuple[str, str, str], ...] = direct_owned_replay_coverage_ranges(
            connection=connection,
            database=clickhouse_database,
        )
    finally:
        delegate.close()

    assert (greenfield_exit_code, settled_exit_code, failed_exit_code) == (0, 0, 1)
    assert "injected failure during selected teardown" in failed_error
    assert failure_coverage == (("_replay_partition=0", "2", "4"),)
    assert (retry_exit_code, retry_error, later_exit_code, later_error) == (0, "", 0, "")
    assert later_rows == ("order-3", "order-4")
    assert later_coverage == (("_replay_partition=0", "3", "4"),)
    assert (earlier_exit_code, earlier_error) == (0, "")
    assert earlier_rows == ("order-2", "order-3", "order-4")
    assert earlier_coverage == (("_replay_partition=0", "2", "4"),)
    assert (ordinary_exit_code, ordinary_error) == (0, "")
    assert final_rows == test_case.expected_target_rows
    assert final_coverage == test_case.expected_coverage


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectAdoptedSourceFailureIntegrationTestCase(
            description="shared adopted table with conflicting mappings is rejected",
            source_table_name="orders_existing",
            source_yml=(
                "sources:\n"
                "  - kind: stream_table\n"
                "    name: orders\n"
                "    table_name: orders_existing\n"
                "    replay_boundary:\n"
                "      mode: offsets\n"
                "      columns:\n"
                "        _replay_partition: event_partition\n"
                "        _replay_offset: event_offset\n"
                "        _replay_timestamp: event_timestamp\n"
                "  - kind: stream_table\n"
                "    name: orders_cursor\n"
                "    table_name: orders_existing\n"
                "    replay_boundary:\n"
                "      mode: cursor\n"
                "      columns:\n"
                "        _replay_cursor: event_cursor\n"
                "        _replay_timestamp: event_timestamp\n"
            ),
            model_sql=_ADOPTED_SOURCE_TEST_CASES[0].model_sql,
            source_columns_sql=(
                "order_id String, event_partition Int32, event_offset Int64, "
                "event_cursor UInt64, event_timestamp DateTime64(3)"
            ),
            expected_error_fragment=(
                "Adopted source table 'orders_existing' has conflicting replay mappings"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_adopted_mappings_when_loading_build_then_discovery_rejects(
    test_case: CliDirectAdoptedSourceFailureIntegrationTestCase,
    tmp_path: Path,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_adopted_source_project(
        project_root=tmp_path,
        source_yml=test_case.source_yml,
        model_sql=test_case.model_sql,
    )
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.{test_case.source_table_name} "
            f"({test_case.source_columns_sql}) ENGINE = MergeTree() ORDER BY order_id"
        )
        source_ddl_before: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.{test_case.source_table_name}"
            ).result_rows[0][0]
        )
        connection: DirectActionRecordingConnection = DirectActionRecordingConnection(delegate)
        with pytest.raises(PipelineDiscoveryError) as rejection:
            _ = run_direct_build(
                project_root=tmp_path,
                database=clickhouse_database,
                connection=connection,
            )
        source_ddl_after: str = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.{test_case.source_table_name}"
            ).result_rows[0][0]
        )
    finally:
        delegate.close()

    assert test_case.expected_error_fragment in str(rejection.value)
    assert source_ddl_after == source_ddl_before
    assert connection.command_statements == []
