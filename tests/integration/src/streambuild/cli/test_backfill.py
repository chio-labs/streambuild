from __future__ import annotations

import builtins

import pytest
from _pytest.capture import CaptureResult
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.backfill.main._run_backfill import run_backfill
from streambuild.cli.backfill.models import BackfillCommandOptions
from tests.integration.src.streambuild.cli._test_types import (
    CliBackfillIntegrationTestCase,
)
from tests.integration.src.streambuild.cli.helpers import (
    BACKFILL_PIPELINES_ROOT,
    SELECTOR_PIPELINES_ROOT,
    build_managed_clickhouse_client,
    ensure_backfill_metadata_tables,
    load_deployment_status_rows,
    load_runtime_execution_modes,
    load_selected_root_names,
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
            prompt_response="",
            expected_exit_code=1,
            expected_output_fragments=(),
            expected_error_fragments=("--json requires --auto-approve for backfill",),
            expected_deployment_status_rows=(),
            expected_absent_output_fragments=("Plan Ready",),
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
            prompt_response="",
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
            expected_absent_output_fragments=("Plan Ready",),
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
            prompt_response="",
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
            prompt_response="",
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
            prompt_response="",
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
            prompt_response="",
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
            expected_absent_output_fragments=("Plan Ready",),
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
    managed_client: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    ensure_backfill_metadata_tables(managed_client=managed_client, database=clickhouse_database)
    monkeypatch.setattr(builtins, "input", lambda _prompt: test_case.prompt_response)

    try:
        exit_code: int = run_backfill(
            options=BackfillCommandOptions(
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
            ),
            client=managed_client,
        )
    finally:
        managed_client.close()

    captured: CaptureResult[str] = capsys.readouterr()
    deployment_status_rows: tuple[tuple[str, ...], ...] = load_deployment_status_rows(
        clickhouse_client=clickhouse_client, database=clickhouse_database
    )
    selected_root_names: tuple[str, ...] = load_selected_root_names(
        clickhouse_client=clickhouse_client, database=clickhouse_database
    )
    runtime_execution_modes: tuple[tuple[str, str | None], ...] = load_runtime_execution_modes(
        clickhouse_client=clickhouse_client, database=clickhouse_database
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
    absent_output_fragment: str
    for absent_output_fragment in test_case.expected_absent_output_fragments:
        assert absent_output_fragment not in captured.out
