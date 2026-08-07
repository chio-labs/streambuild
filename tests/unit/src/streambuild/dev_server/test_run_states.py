from datetime import UTC, datetime, timedelta

import pytest

from streambuild.adapter.models import AdapterQueryResult
from streambuild.dev_server._helpers.runs_query import derive_run_status, read_run_events
from streambuild.dev_server.types import RunPresentationStatus
from tests.unit.src.streambuild.dev_server._test_types import (
    MissingRunDetailTestCase,
    RunDetailHistoryTestCase,
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
