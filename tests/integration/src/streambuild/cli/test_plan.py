from pathlib import Path

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import CatalogSnapshot
from streambuild.cli.plan.main._run_plan import run_plan
from streambuild.cli.plan.main._warnings import add_empty_replay_source_warnings
from streambuild.compiler.compile.models import (
    Column,
    DesiredState,
    DesiredTable,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.constants import (
    REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    REBUILD_STRATEGY_SHADOW,
)
from streambuild.compiler.planner.main.load_planning_warehouse_snapshot import (
    load_planning_warehouse_snapshot,
)
from streambuild.compiler.planner.models import (
    DeploymentPlan,
    PlanningWarehouseSnapshot,
    RebuildSubtree,
)
from streambuild.executor.backfill.main.resolve_unsupported_bounded_replay_behavior import (
    resolve_unsupported_bounded_replay_behavior,
)
from tests.integration.src.streambuild.cli._test_types import (
    CliBoundedPlanSnapshotIntegrationTestCase,
    CliPlanSnapshotIntegrationTestCase,
)
from tests.integration.src.streambuild.cli.helpers import (
    RecordingDelegatingConnection,
    build_managed_clickhouse_client,
    write_adopted_source_plan_project,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliPlanSnapshotIntegrationTestCase(
            description="validates an adopted source through the real catalog snapshot",
            expected_exit_code=0,
            expected_output_fragment="Plan Ready",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_adopted_source_when_planning_then_snapshot_validation_succeeds(
    test_case: CliPlanSnapshotIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pipelines_root: Path = write_adopted_source_plan_project(tmp_path / "project")
    client: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    client.command(
        f"CREATE TABLE {clickhouse_database}.orders_existing "
        "(order_id String, event_timestamp DateTime64(3)) "
        "ENGINE = MergeTree ORDER BY order_id"
    )

    try:
        exit_code: int = run_plan(
            pipelines_root=pipelines_root,
            database=clickhouse_database,
            selectors=(),
            full_refresh=False,
            start_time=None,
            json_output=False,
            verbose=False,
            client=client,
        )
    finally:
        client.close()

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_output_fragment in capsys.readouterr().out


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliBoundedPlanSnapshotIntegrationTestCase(
            description="resolves a history-preserving bounded plan from one real snapshot",
            start_time="2026-07-26 12:00:00.000",
            expected_execution_mode="seeded_bounded_rebuild",
            expected_warning_count=1,
            expected_catalog_load_count=1,
            expected_query_count=6,
            expected_point_in_time_query_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_bounded_root_when_planning_then_one_snapshot_preserves_resolution(
    test_case: CliBoundedPlanSnapshotIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
) -> None:
    delegate: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    client: RecordingDelegatingConnection = RecordingDelegatingConnection(delegate)
    client.command(
        f"CREATE TABLE {clickhouse_database}.orders_existing "
        "(order_id String, event_timestamp DateTime64(3)) "
        "ENGINE = MergeTree ORDER BY order_id"
    )
    client.command(
        f"CREATE TABLE {clickhouse_database}.tbl__orders_enriched__dep_a "
        "(order_id String, _replay_timestamp DateTime64(3)) "
        "ENGINE = MergeTree ORDER BY order_id"
    )
    client.command(
        f"CREATE VIEW {clickhouse_database}.tbl__orders_enriched AS "
        f"SELECT * FROM {clickhouse_database}.tbl__orders_enriched__dep_a"
    )
    source_key: ObjectKey = ObjectKey(None, "table", "orders_existing")
    root_key: ObjectKey = ObjectKey(None, "table", "tbl__orders_enriched")
    desired_state: DesiredState = DesiredState(
        objects=(
            DesiredTable(
                key=root_key,
                deps=(source_key,),
                spec=TableSpec(
                    columns=(
                        Column(name="order_id", type="String"),
                        Column(name="_replay_timestamp", type="DateTime64(3)"),
                    ),
                    storage=TableStorage(engine="MergeTree()", order_by=("order_id",)),
                ),
            ),
        ),
        replay_anchor_keys=frozenset({source_key}),
        mutable_ref_warning_keys=frozenset(),
    )
    plan: DeploymentPlan = DeploymentPlan(
        deployment_id=None,
        object_changes=(),
        rebuild_subtrees=(
            RebuildSubtree(
                root_key=root_key,
                affected_keys=(root_key,),
                upstream_boundary_key=source_key,
                strategy=REBUILD_STRATEGY_SHADOW,
                execution_mode=REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
                forced_start_time=test_case.start_time,
            ),
        ),
        steps=(),
        prepared_shadow_objects=(),
        warnings=(),
    )

    try:
        snapshot: PlanningWarehouseSnapshot = load_planning_warehouse_snapshot(
            client=client,
            database=clickhouse_database,
        )
        catalog: CatalogSnapshot = snapshot.catalog
        resolved_plan: DeploymentPlan = resolve_unsupported_bounded_replay_behavior(
            catalog=catalog,
            deployment_plan=plan,
            desired_state=desired_state,
            default_database=clickhouse_database,
            replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
        )
        resolved_plan = add_empty_replay_source_warnings(
            client=client,
            catalog=catalog,
            database=clickhouse_database,
            desired_state=desired_state,
            plan=resolved_plan,
        )
    finally:
        client.close()

    point_in_time_query_count: int = sum(
        statement.startswith("SELECT count() FROM ") for statement in client.query_statements
    )
    assert (
        str(resolved_plan.rebuild_subtrees[0].execution_mode) == test_case.expected_execution_mode
    )
    assert resolved_plan.rebuild_subtrees[0].history_preserving_bounded_supported
    assert len(resolved_plan.warnings) == test_case.expected_warning_count
    assert client.catalog_load_count == test_case.expected_catalog_load_count
    assert len(client.query_statements) == test_case.expected_query_count
    assert point_in_time_query_count == test_case.expected_point_in_time_query_count
