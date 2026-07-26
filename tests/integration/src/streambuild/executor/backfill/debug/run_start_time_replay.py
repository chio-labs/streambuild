from __future__ import annotations

import argparse
import uuid

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from streambuild.compiler.planner.models import RebuildSubtree
from tests.integration.src.streambuild.conftest import start_clickhouse_container
from tests.integration.src.streambuild.executor.backfill._test_types import (
    ExecuteStartTimeReplayIntegrationTestCase,
)
from tests.integration.src.streambuild.executor.backfill.scenario_models import (
    StartTimeReplayScenarioResult,
)
from tests.integration.src.streambuild.executor.backfill.scenarios import (
    run_start_time_replay_scenario,
)
from tests.integration.src.streambuild.executor.backfill.test_main import (
    test_given_start_time_offset_replay_when_executing_then_it_replays_expected_rows,
    test_given_start_time_scalar_replay_when_executing_then_it_replays_expected_rows,
)


def main() -> int:
    args: argparse.Namespace = _build_parser().parse_args()
    test_case: ExecuteStartTimeReplayIntegrationTestCase = _resolve_test_case(
        mode=args.mode,
        window=args.window,
    )

    with start_clickhouse_container() as connection_settings:
        client: Client = clickhouse_connect.get_client(
            host=connection_settings.host,
            port=connection_settings.port,
            username=connection_settings.username,
            password=connection_settings.password,
        )
        database_name: str = f"streambuild_debug_{uuid.uuid4().hex[:12]}"
        client.command(f"CREATE DATABASE {database_name}")
        try:
            scenario_result: StartTimeReplayScenarioResult = run_start_time_replay_scenario(
                test_case=test_case,
                connection_settings=connection_settings,
                clickhouse_client=client,
                clickhouse_database=database_name,
            )
            _print_result(scenario_result)
            if args.pause:
                input(
                    "Paused for inspection. Press Enter to tear down the container and database..."
                )
        finally:
            if not args.keep_db:
                client.command(f"DROP DATABASE IF EXISTS {database_name} SYNC")
            client.close()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Run the local start-time replay debug scenario"
    )
    parser.add_argument("--mode", choices=("scalar", "offset"), default="scalar")
    parser.add_argument("--window", choices=("tail", "full-history"), default="tail")
    parser.add_argument("--keep-db", action="store_true")
    parser.add_argument("--pause", action="store_true")
    return parser


def _parametrized_cases(
    *, test_function: object
) -> list[ExecuteStartTimeReplayIntegrationTestCase]:
    """Read cases off the test's parametrize mark.

    The cases are declared inline in the decorator so they stay visible beside the
    test, so this debug tool reads them from the mark rather than duplicating them.
    """

    marks = getattr(test_function, "pytestmark", ())
    for mark in marks:
        if mark.name == "parametrize":
            return list(mark.args[1])
    raise ValueError("Test function has no parametrize mark.")


def _resolve_test_case(*, mode: str, window: str) -> ExecuteStartTimeReplayIntegrationTestCase:
    test_cases: list[ExecuteStartTimeReplayIntegrationTestCase] = _parametrized_cases(
        test_function=(
            test_given_start_time_scalar_replay_when_executing_then_it_replays_expected_rows
            if mode == "scalar"
            else test_given_start_time_offset_replay_when_executing_then_it_replays_expected_rows
        )
    )
    expected_fragment: str = (
        "full available window" if window == "full-history" else "explicit tail"
    )
    test_case: ExecuteStartTimeReplayIntegrationTestCase
    for test_case in test_cases:
        if expected_fragment in test_case.description:
            return test_case
    raise ValueError(f"No debug scenario found for mode={mode!r} window={window!r}")


def _print_result(result: StartTimeReplayScenarioResult) -> None:
    subtree: RebuildSubtree = result.start_time_result.bootstrap.deployment_plan.rebuild_subtrees[0]
    print(f"ClickHouse: http://{result.connection_settings.host}:{result.connection_settings.port}")
    print(f"Database: {result.database}")
    print(f"Deployment: {result.start_time_result.bootstrap.deployment_id}")
    print(f"Converted start time: {result.converted_start_time}")
    print(f"Execution mode: {subtree.execution_mode}")
    print(f"Shadow rows: {result.shadow_rows}")
    print("Inspect shadow rows:")
    print(
        "  "
        "curl -sS 'http://{host}:{port}/?user={user}&password={password}' --data-binary \""
        'SELECT * FROM {database}.{table} ORDER BY order_id"'.format(
            host=result.connection_settings.host,
            port=result.connection_settings.port,
            user=result.connection_settings.username,
            password=result.connection_settings.password,
            database=result.database,
            table=result.start_time_result.bootstrap.deployment_plan.prepared_shadow_objects[
                0
            ].physical_name,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
