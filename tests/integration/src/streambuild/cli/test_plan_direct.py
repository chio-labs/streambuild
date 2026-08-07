from pathlib import Path

import pytest
from _pytest.capture import CaptureResult
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from tests.integration.src.streambuild.cli._test_types import CliDirectPlanIntegrationTestCase
from tests.integration.src.streambuild.cli.helpers import (
    build_managed_clickhouse_client,
    plan_relation_operations,
    plan_replay_root_models,
    plan_scope_names,
    run_direct_plan,
    settle_direct_scope_warehouse,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.unit.src.streambuild.compiler.planner.helpers import write_direct_scope_project


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectPlanIntegrationTestCase(
            description="an unchanged warehouse plans the identical complete direct workflow",
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_replay_root_models=("alpha",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_direct_warehouse_when_planning_twice_then_workflow_is_stable(
    test_case: CliDirectPlanIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    write_direct_scope_project(project_root=tmp_path)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings, database=clickhouse_database
    )

    try:
        settle_direct_scope_warehouse(
            connection=connection,
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            create_relations=False,
        )
        relation_query: str = (
            f"SELECT name FROM system.tables WHERE database = '{clickhouse_database}' ORDER BY name"
        )
        before_relation_names: tuple[str, ...] = tuple(
            str(row[0]) for row in clickhouse_client.query(relation_query).result_rows
        )
        initial_exit_code: int = run_direct_plan(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        initial_capture: CaptureResult[str] = capsys.readouterr()
        initial_output: str = initial_capture.out
        first_exit_code: int = run_direct_plan(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        first_capture: CaptureResult[str] = capsys.readouterr()
        first_output: str = first_capture.out
        second_exit_code: int = run_direct_plan(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        second_capture: CaptureResult[str] = capsys.readouterr()
        second_output: str = second_capture.out
        after_relation_names: tuple[str, ...] = tuple(
            str(row[0]) for row in clickhouse_client.query(relation_query).result_rows
        )
    finally:
        connection.close()

    assert (initial_exit_code, first_exit_code, second_exit_code) == (0, 0, 0), (
        initial_capture.err,
        first_capture.err,
        second_capture.err,
    )
    assert first_output == second_output
    artifact_root: Path = tmp_path / "target/run/plan"
    step_paths: tuple[Path, ...] = tuple(sorted((artifact_root / "steps").glob("*.sql.template")))
    assert before_relation_names == after_relation_names
    assert step_paths
    assert (artifact_root / "workflow.template.sql").read_bytes() == b"\n".join(
        path.read_bytes() for path in step_paths
    )
    assert plan_scope_names(plan_json=first_output) == test_case.expected_execution_scope
    assert plan_scope_names(plan_json=initial_output) == test_case.expected_execution_scope
    assert plan_relation_operations(plan_json=initial_output) == plan_relation_operations(
        plan_json=first_output
    )
    assert plan_replay_root_models(plan_json=first_output) == test_case.expected_replay_root_models
