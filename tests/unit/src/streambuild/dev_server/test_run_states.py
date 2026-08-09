from datetime import UTC, datetime, timedelta

import pytest

from streambuild.adapter.models import AdapterQueryResult
from streambuild.dev_server._helpers.queries.runs_query import (
    _assemble_runs,
    derive_run_duration_ms,
    derive_run_status,
    read_latest_direct_build_materialization,
    read_run_events,
)
from streambuild.dev_server.types import RunPresentationStatus
from tests.unit.src.streambuild.dev_server._test_types import (
    DevRefactorTestCase,
    MissingRunDetailTestCase,
    RunDetailHistoryTestCase,
    RunDurationDerivationTestCase,
    RunStatusDerivationTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    FakeAdapterConnection,
    build_fake_state_connection,
)

_WAREHOUSE_NOW: datetime = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    [
        DevRefactorTestCase(
            description="terminal run presentation uses the richer started-event command",
            expected_value="stb build --target test --select orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_full_started_command_when_assembling_terminal_run_then_uses_full_command(
    test_case: DevRefactorTestCase,
) -> None:
    runs: list[dict[str, object]] = _assemble_runs(
        terminal_by_id={
            "inv-1": {
                "invocationId": "inv-1",
                "command": "build",
                "startedAt": "2026-08-07 11:00:00.000",
                "lastSignalAt": "2026-08-07 11:01:00.000",
            }
        },
        streams={
            "inv-1": [
                {
                    "event": "run_started",
                    "emittedAt": "2026-08-07 11:00:00.000",
                    "command": "build",
                    "displayCommand": "stb build --target test --select orders",
                },
                {
                    "event": "run_completed",
                    "emittedAt": "2026-08-07 11:01:00.000",
                },
            ]
        },
        warehouse_now=_WAREHOUSE_NOW,
        limit=None,
    )

    assert runs[0]["command"] == "build"
    assert runs[0]["displayCommand"] == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        DevRefactorTestCase(
            description="cancelled direct build cannot supersede failed materialization evidence",
            expected_value="failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cancelled_build_after_failure_when_reading_guard_then_latest_non_null_wins(
    test_case: DevRefactorTestCase,
) -> None:
    table_query: str = (
        "SELECT count() AS present FROM system.tables "
        "WHERE database = 'analytics' AND name = '_streambuild_invocations'"
    )
    materialization_query: str = (
        "SELECT materialized_outcome FROM `analytics`.`_streambuild_invocations` WHERE "
        "project_identity = '/project' AND target_identity = 'analytics' AND command = 'build' "
        "AND mode = 'direct' AND materialized_outcome IS NOT NULL "
        "ORDER BY completed_at DESC, invocation_id DESC LIMIT 1"
    )
    connection: FakeAdapterConnection = FakeAdapterConnection(
        catalog=build_fake_state_connection()._catalog,
        results_by_query={
            table_query: AdapterQueryResult(column_names=("present",), rows=((1,),)),
            materialization_query: AdapterQueryResult(
                column_names=("materialized_outcome",),
                rows=(("failed",),),
            ),
        },
        warehouse_timestamp="2026-08-08 12:00:00.000",
    )

    outcome: str | None = read_latest_direct_build_materialization(
        connection=connection,
        database="analytics",
        project_identity="/project",
    )

    assert outcome == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        RunStatusDerivationTestCase(
            description="fresh signal is running",
            terminal_outcome=None,
            completed_event_outcome=None,
            signal_age_seconds=10,
            expected_status=RunPresentationStatus.RUNNING,
        ),
        RunStatusDerivationTestCase(
            description="short silence is reversible unresponsive state",
            terminal_outcome=None,
            completed_event_outcome=None,
            signal_age_seconds=45,
            expected_status=RunPresentationStatus.UNRESPONSIVE,
        ),
        RunStatusDerivationTestCase(
            description="long silence is presumed failed",
            terminal_outcome=None,
            completed_event_outcome=None,
            signal_age_seconds=600,
            expected_status=RunPresentationStatus.PRESUMED_FAILED,
        ),
        RunStatusDerivationTestCase(
            description="terminal invocation overrides stale signals",
            terminal_outcome="succeeded",
            completed_event_outcome=None,
            signal_age_seconds=1200,
            expected_status=RunPresentationStatus.SUCCEEDED,
        ),
        RunStatusDerivationTestCase(
            description="completed event supplies terminal fact when invocation is absent",
            terminal_outcome=None,
            completed_event_outcome="cancelled",
            signal_age_seconds=1200,
            expected_status=RunPresentationStatus.CANCELLED,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_run_facts_when_deriving_status_then_fact_and_liveness_contract_is_preserved(
    test_case: RunStatusDerivationTestCase,
) -> None:
    status: RunPresentationStatus = derive_run_status(
        terminal_outcome=test_case.terminal_outcome,
        completed_event_outcome=test_case.completed_event_outcome,
        last_signal_at=_WAREHOUSE_NOW - timedelta(seconds=test_case.signal_age_seconds),
        warehouse_now=_WAREHOUSE_NOW,
    )

    assert status == test_case.expected_status


@pytest.mark.parametrize(
    "test_case",
    [
        RunDurationDerivationTestCase(
            description="completed event stream uses terminal duration",
            started_at="2026-08-07 11:00:00.000",
            completed_at="2026-08-07 11:05:00.000",
            warehouse_now=_WAREHOUSE_NOW,
            expected_duration_ms=300_000,
        ),
        RunDurationDerivationTestCase(
            description="active event stream uses current elapsed time",
            started_at="2026-08-07 11:00:00.000",
            completed_at=None,
            warehouse_now=_WAREHOUSE_NOW,
            expected_duration_ms=3_600_000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_event_stream_timestamps_when_deriving_duration_then_uses_correct_end(
    test_case: RunDurationDerivationTestCase,
) -> None:
    duration_ms: int = derive_run_duration_ms(
        started_at=test_case.started_at,
        completed_at=test_case.completed_at,
        warehouse_now=test_case.warehouse_now,
    )

    assert duration_ms == test_case.expected_duration_ms


@pytest.mark.parametrize(
    "test_case",
    [
        RunDetailHistoryTestCase(
            description="terminal detail remains available outside the run-list window",
            invocation_id="old-invocation",
            expected_status="succeeded",
            expected_found=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_old_terminal_run_when_reading_detail_then_status_is_not_limited_by_run_list(
    test_case: RunDetailHistoryTestCase,
) -> None:
    invocation_table_query: str = (
        "SELECT count() AS present FROM system.tables "
        "WHERE database = 'analytics' AND name = '_streambuild_invocations'"
    )
    invocation_query: str = (
        "SELECT invocation_id, command, mode, outcome, exit_code, "
        "toString(started_at) AS started_at, toString(completed_at) AS completed_at, "
        "duration_ms, selected_node_count, error_message, tool_version "
        "FROM `analytics`.`_streambuild_invocations` "
        f"WHERE invocation_id = '{test_case.invocation_id}' ORDER BY started_at DESC"
    )
    event_table_query: str = (
        "SELECT count() AS present FROM system.tables "
        "WHERE database = 'analytics' AND name = '_streambuild_run_events'"
    )
    connection: FakeAdapterConnection = FakeAdapterConnection(
        catalog=build_fake_state_connection()._catalog,
        warehouse_timestamp="2026-08-07 12:00:00.000",
        results_by_query={
            invocation_table_query: AdapterQueryResult(rows=((1,),), column_names=("present",)),
            invocation_query: AdapterQueryResult(
                rows=(
                    (
                        test_case.invocation_id,
                        "build",
                        "direct",
                        "succeeded",
                        0,
                        "2026-01-01 00:00:00.000",
                        "2026-01-01 00:01:00.000",
                        60000,
                        1,
                        None,
                        "0.7.0",
                    ),
                ),
                column_names=(
                    "invocation_id",
                    "command",
                    "mode",
                    "outcome",
                    "exit_code",
                    "started_at",
                    "completed_at",
                    "duration_ms",
                    "selected_node_count",
                    "error_message",
                    "tool_version",
                ),
            ),
            event_table_query: AdapterQueryResult(rows=((0,),), column_names=("present",)),
        },
    )

    payload: dict[str, object] = read_run_events(
        connection=connection,
        database="analytics",
        invocation_id=test_case.invocation_id,
    )

    assert payload["status"] == test_case.expected_status
    assert payload["found"] is test_case.expected_found


@pytest.mark.parametrize(
    "test_case",
    [
        MissingRunDetailTestCase(
            description="unknown invocation is explicitly absent",
            invocation_id="missing-invocation",
            expected_status=None,
            expected_found=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_run_when_reading_detail_then_absence_is_explicit(
    test_case: MissingRunDetailTestCase,
) -> None:
    invocation_table_query: str = (
        "SELECT count() AS present FROM system.tables "
        "WHERE database = 'analytics' AND name = '_streambuild_invocations'"
    )
    event_table_query: str = (
        "SELECT count() AS present FROM system.tables "
        "WHERE database = 'analytics' AND name = '_streambuild_run_events'"
    )
    connection: FakeAdapterConnection = FakeAdapterConnection(
        catalog=build_fake_state_connection()._catalog,
        warehouse_timestamp="2026-08-07 12:00:00.000",
        results_by_query={
            invocation_table_query: AdapterQueryResult(rows=((0,),), column_names=("present",)),
            event_table_query: AdapterQueryResult(rows=((0,),), column_names=("present",)),
        },
    )

    payload: dict[str, object] = read_run_events(
        connection=connection,
        database="analytics",
        invocation_id=test_case.invocation_id,
    )

    assert payload["status"] == test_case.expected_status
    assert payload["found"] is test_case.expected_found
