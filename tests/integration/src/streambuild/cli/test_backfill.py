from __future__ import annotations

import builtins

import pytest
from _pytest.capture import CaptureResult
from clickhouse_connect.driver.client import Client

from streambuild.cli.backfill.main.run_backfill import run_backfill
from streambuild.integrations.clickhouse.client import ClickHouseClient
from tests.integration.src.streambuild.cli._test_types import (
    CliBackfillIntegrationTestCase,
)
from tests.integration.src.streambuild.cli.helpers import (
    BACKFILL_PIPELINES_ROOT,
    SELECTOR_PIPELINES_ROOT,
    build_deployment_status_query,
    build_managed_clickhouse_client,
    build_runtime_details_table_query,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliBackfillIntegrationTestCase(
            description="rejects json backfill without auto approve",
            pipelines_root=BACKFILL_PIPELINES_ROOT,
            selectors=(),
            full_refresh=False,
            start_time=None,
            json_output=True,
            verbose=False,
            auto_approve=False,
            prompt_response=None,
            expected_exit_code=1,
            expected_output_fragments=(),
            expected_error_fragments=("--json requires --auto-approve for backfill",),
            expected_deployment_status_rows=(),
        ),
        CliBackfillIntegrationTestCase(
            description="cancels interactive backfill when prompt is declined",
            pipelines_root=BACKFILL_PIPELINES_ROOT,
            selectors=(),
            full_refresh=False,
            start_time=None,
            json_output=False,
            verbose=False,
            auto_approve=False,
            prompt_response="n",
            expected_exit_code=1,
            expected_output_fragments=("Plan Ready", "Backfill cancelled."),
            expected_error_fragments=(),
            expected_deployment_status_rows=(),
        ),
        CliBackfillIntegrationTestCase(
            description="executes json backfill with auto approve without printing plan preview",
            pipelines_root=BACKFILL_PIPELINES_ROOT,
            selectors=(),
            full_refresh=False,
            start_time=None,
            json_output=True,
            verbose=False,
            auto_approve=True,
            prompt_response=None,
            expected_exit_code=0,
            expected_output_fragments=(
                '"deployment_id":',
                '"boundary_time":',
                '"root_reports":',
                '"state_kind": "greenfield"',
                '"replay_strategy": "create_from_scratch"',
            ),
            expected_error_fragments=(),
            expected_deployment_status_rows=(("backfilling",),),
            expected_selected_root_names=("tbl__orders_enriched",),
            expected_runtime_execution_modes=(("tbl__orders_enriched", "full_rebuild"),),
        ),
        CliBackfillIntegrationTestCase(
            description="rejects full refresh without selectors",
            pipelines_root=BACKFILL_PIPELINES_ROOT,
            selectors=(),
            full_refresh=True,
            start_time=None,
            json_output=False,
            verbose=False,
            auto_approve=True,
            prompt_response=None,
            expected_exit_code=1,
            expected_output_fragments=(),
            expected_error_fragments=("--full-refresh requires at least one --select",),
            expected_deployment_status_rows=(),
        ),
        CliBackfillIntegrationTestCase(
            description="rejects start time for roots without an active published view",
            pipelines_root=BACKFILL_PIPELINES_ROOT,
            selectors=("orders_enriched",),
            full_refresh=False,
            start_time="2026-04-01T00:00:00Z",
            json_output=False,
            verbose=False,
            auto_approve=True,
            prompt_response=None,
            expected_exit_code=1,
            expected_output_fragments=(),
            expected_error_fragments=("--start-time requires an active published root",),
            expected_deployment_status_rows=(),
        ),
        CliBackfillIntegrationTestCase(
            description="rejects combining full refresh with start time",
            pipelines_root=BACKFILL_PIPELINES_ROOT,
            selectors=("orders_enriched",),
            full_refresh=True,
            start_time="2026-04-01T00:00:00Z",
            json_output=False,
            verbose=False,
            auto_approve=True,
            prompt_response=None,
            expected_exit_code=1,
            expected_output_fragments=(),
            expected_error_fragments=("--full-refresh cannot be combined with --start-time",),
            expected_deployment_status_rows=(),
        ),
        CliBackfillIntegrationTestCase(
            description="executes selected full refresh for one authored model subtree",
            pipelines_root=SELECTOR_PIPELINES_ROOT,
            selectors=("orders_clean",),
            full_refresh=True,
            start_time=None,
            json_output=True,
            verbose=False,
            auto_approve=True,
            prompt_response=None,
            expected_exit_code=0,
            expected_output_fragments=(
                '"deployment_id":',
                '"root_reports":',
            ),
            expected_error_fragments=(),
            expected_deployment_status_rows=(("backfilling",),),
            expected_selected_root_names=("tbl__orders_clean",),
            expected_runtime_execution_modes=(
                ("tbl__orders_clean", "full_rebuild"),
                ("tbl__orders_enriched", "full_rebuild"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_backfill_command_when_running_then_it_behaves_as_expected(
    test_case: CliBackfillIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    managed_client: ClickHouseClient = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    if test_case.prompt_response is not None:
        monkeypatch.setattr(builtins, "input", lambda _prompt: test_case.prompt_response)

    try:
        exit_code: int = run_backfill(
            pipelines_root=test_case.pipelines_root,
            database=clickhouse_database,
            metadata_database=clickhouse_database,
            selectors=test_case.selectors,
            deployment_id=None,
            full_refresh=test_case.full_refresh,
            start_time=test_case.start_time,
            json_output=test_case.json_output,
            verbose=test_case.verbose,
            auto_approve=test_case.auto_approve,
            client=managed_client,
        )
    finally:
        managed_client.close()

    captured: CaptureResult[str] = capsys.readouterr()
    metadata_table_exists: bool = bool(
        clickhouse_client.query(build_deployment_status_query(clickhouse_database)).result_rows
    )
    runtime_details_table_exists: bool = bool(
        clickhouse_client.query(build_runtime_details_table_query(clickhouse_database)).result_rows
    )
    deployment_status_rows: tuple[tuple[str, ...], ...] = ()
    selected_root_names: tuple[str, ...] = ()
    runtime_execution_modes: tuple[tuple[str, str | None], ...] = ()
    if metadata_table_exists:
        deployment_status_query: str = (
            f"SELECT status FROM {clickhouse_database}.streambuild_deployments "
            "ORDER BY deployment_id"
        )
        deployment_status_rows = tuple(
            tuple(str(value) for value in row)
            for row in clickhouse_client.query(deployment_status_query).result_rows
        )
        selected_root_names_query: str = (
            "SELECT JSONExtractString(root_key, 'name') FROM "
            f"{clickhouse_database}.streambuild_deployments "
            "ARRAY JOIN JSONExtractArrayRaw(selected_root_keys_json) AS root_key "
            "ORDER BY JSONExtractString(root_key, 'name')"
        )
        selected_root_names = tuple(
            str(row[0]) for row in clickhouse_client.query(selected_root_names_query).result_rows
        )
    if runtime_details_table_exists:
        runtime_details_query: str = (
            f"SELECT root_object_name, execution_mode "
            f"FROM {clickhouse_database}.streambuild_deployment_runtime_details "
            "ORDER BY root_object_name"
        )
        runtime_execution_modes = tuple(
            (str(row[0]), None if row[1] is None else str(row[1]))
            for row in clickhouse_client.query(runtime_details_query).result_rows
        )

    assert exit_code == test_case.expected_exit_code
    expected_output_fragment: str
    for expected_output_fragment in test_case.expected_output_fragments:
        assert expected_output_fragment in captured.out
    expected_error_fragment: str
    for expected_error_fragment in test_case.expected_error_fragments:
        assert expected_error_fragment in captured.err
    assert deployment_status_rows == test_case.expected_deployment_status_rows
    assert selected_root_names == test_case.expected_selected_root_names
    assert runtime_execution_modes == test_case.expected_runtime_execution_modes
    if test_case.json_output:
        assert "Plan Ready" not in captured.out
