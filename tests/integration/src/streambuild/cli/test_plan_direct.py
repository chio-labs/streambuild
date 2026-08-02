from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from tests.integration.src.streambuild.cli._test_types import CliDirectPlanIntegrationTestCase
from tests.integration.src.streambuild.cli.helpers import (
    build_managed_clickhouse_client,
    plan_ownership_labels,
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
            description="a settled warehouse still plans the identical complete closure",
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_replay_root_models=("alpha",),
            expected_initial_ownership=("absent",),
            expected_settled_ownership=("direct",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_settled_direct_warehouse_when_planning_twice_then_closure_never_shrinks(
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
            record_ownership=False,
        )
        initial_exit_code: int = run_direct_plan(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        initial_output: str = capsys.readouterr().out
        settle_direct_scope_warehouse(
            connection=connection,
            clickhouse_client=clickhouse_client,
            database=clickhouse_database,
            record_ownership=True,
        )
        first_exit_code: int = run_direct_plan(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        first_output: str = capsys.readouterr().out
        second_exit_code: int = run_direct_plan(
            project_root=tmp_path, database=clickhouse_database, connection=connection
        )
        second_output: str = capsys.readouterr().out
    finally:
        connection.close()

    assert (initial_exit_code, first_exit_code, second_exit_code) == (0, 0, 0)
    assert first_output == second_output
    assert plan_scope_names(plan_json=first_output) == test_case.expected_execution_scope
    assert plan_scope_names(plan_json=initial_output) == test_case.expected_execution_scope
    assert plan_relation_operations(plan_json=initial_output) == plan_relation_operations(
        plan_json=first_output
    )
    assert plan_replay_root_models(plan_json=first_output) == test_case.expected_replay_root_models
    assert plan_ownership_labels(plan_json=initial_output) == test_case.expected_initial_ownership
    assert plan_ownership_labels(plan_json=first_output) == test_case.expected_settled_ownership
