from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterQueryResult, AdapterStatementProgress
from streambuild.dev_server._helpers.queries import runs_query
from streambuild.dev_server._helpers.queries.runs_query import (
    _assemble_runs,
    _statement_progress,
    _terminal_audit_summary,
    _terminal_runs,
    derive_run_duration_ms,
    derive_run_status,
    read_latest_direct_build_materialization,
    read_run_events,
    read_run_statement,
    read_runs,
)
from streambuild.dev_server.types import RunPresentationStatus
from tests.unit.src.streambuild.dev_server._test_types import (
    DevRefactorTestCase,
    MissingRunDetailTestCase,
    RunDetailHistoryTestCase,
    RunDurationDerivationTestCase,
    RunHistoryQueryTestCase,
    RunStatementReadTestCase,
    RunStatusDerivationTestCase,
    TerminalRunQueryTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    FakeAdapterConnection,
    build_fake_state_connection,
)

_WAREHOUSE_NOW: datetime = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


class RunHistoryClockConnection:
    def capture_warehouse_timestamp(self) -> str:
        return "2026-08-07 12:00:00.000"


class StatementProgressConnection:
    def load_statement_progress(self, *, query_id: str) -> AdapterStatementProgress | None:
        assert query_id == "query-123"
        return AdapterStatementProgress(
            elapsed_seconds=10.0,
            read_rows=100,
            read_bytes=200,
            total_rows_approx=1000,
            memory_usage_bytes=300,
            settings=(("max_threads", "1"),),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        RunHistoryQueryTestCase(
            description="scheduled cycles do not displace recent builds",
            expected_invocation_ids=frozenset({"build-run", "audit-cycle"}),
            expected_terminal_calls=((100, False), (25, True)),
            expected_exclude_terminal_invocations=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scheduled_cycles_fill_history_when_reading_runs_then_builds_remain_visible(
    monkeypatch: pytest.MonkeyPatch,
    test_case: RunHistoryQueryTestCase,
) -> None:
    terminal_calls: list[tuple[int | None, bool | None]] = []
    active_calls: list[dict[str, object]] = []
    started_invocations: list[tuple[str, ...]] = []
    table_checks: list[str] = []

    terminal_payloads: dict[bool | None, dict[str, dict[str, object]]] = {
        False: {
            "build-run": {
                "invocationId": "build-run",
                "command": "build",
                "mode": "direct",
                "status": "succeeded",
                "startedAt": "2026-08-07 11:00:00.000",
                "lastSignalAt": "2026-08-07 11:01:00.000",
            }
        },
        True: {
            "audit-cycle": {
                "invocationId": "audit-cycle",
                "command": "audit",
                "mode": "scheduled",
                "status": "succeeded",
                "startedAt": "2026-08-07 11:00:00.000",
                "lastSignalAt": "2026-08-07 11:01:00.000",
            }
        },
    }

    def terminal_runs(
        *,
        connection: AdapterConnection,
        database: str,
        invocation_id: str | None = None,
        limit: int | None = None,
        scheduled: bool | None = None,
        table_exists: bool | None = None,
    ) -> dict[str, dict[str, object]]:
        del connection, database, invocation_id
        assert table_exists is True
        terminal_calls.append((limit, scheduled))
        return terminal_payloads[scheduled]

    monkeypatch.setattr(runs_query, "_terminal_runs", terminal_runs)

    def table_exists(**kwargs: object) -> bool:
        table_checks.append(str(kwargs["table"]))
        return True

    monkeypatch.setattr(runs_query, "_table_exists", table_exists)
    monkeypatch.setattr(
        runs_query,
        "_run_started_streams",
        lambda **kwargs: started_invocations.append(kwargs["invocation_ids"]) or {},
    )
    monkeypatch.setattr(
        runs_query,
        "_event_streams",
        lambda **kwargs: active_calls.append(kwargs) or {},
    )

    connection: AdapterConnection = cast(AdapterConnection, RunHistoryClockConnection())
    runs: list[dict[str, object]] = read_runs(
        connection=connection,
        database="analytics",
    )

    assert {run["invocationId"] for run in runs} == test_case.expected_invocation_ids
    assert terminal_calls == list(test_case.expected_terminal_calls)
    assert table_checks == ["_streambuild_invocations", "_streambuild_run_events"]
    assert started_invocations == [("build-run", "audit-cycle")]
    assert active_calls == [
        {
            "connection": connection,
            "database": "analytics",
            "recent_limit": 400,
            "active_only": True,
            "exclude_terminal_invocations": test_case.expected_exclude_terminal_invocations,
            "table_exists": True,
        }
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        RunHistoryQueryTestCase(
            description="event-only metadata remains readable",
            expected_invocation_ids=frozenset(),
            expected_terminal_calls=(),
            expected_exclude_terminal_invocations=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_invocation_table_when_reading_runs_then_active_events_remain_supported(
    monkeypatch: pytest.MonkeyPatch,
    test_case: RunHistoryQueryTestCase,
) -> None:
    active_calls: list[dict[str, object]] = []
    monkeypatch.setattr(runs_query, "_table_exists", lambda **_: False)
    monkeypatch.setattr(
        runs_query,
        "_terminal_runs",
        lambda **_: pytest.fail("terminal runs must not be read without an invocation table"),
    )
    monkeypatch.setattr(runs_query, "_run_started_streams", lambda **_: {})
    monkeypatch.setattr(
        runs_query,
        "_event_streams",
        lambda **kwargs: active_calls.append(kwargs) or {},
    )

    read_runs(
        connection=cast(AdapterConnection, RunHistoryClockConnection()),
        database="analytics",
    )

    assert active_calls[0]["exclude_terminal_invocations"] is (
        test_case.expected_exclude_terminal_invocations
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TerminalRunQueryTestCase(
            description="legacy null mode build remains visible",
            invocation_id="legacy-build",
            expected_command="build",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_null_mode_build_when_reading_terminal_operations_then_it_is_not_excluded(
    test_case: TerminalRunQueryTestCase,
) -> None:
    invocation_table_query: str = (
        "SELECT count() AS present FROM system.tables "
        "WHERE database = 'analytics' AND name = '_streambuild_invocations'"
    )
    invocation_query: str = (
        "SELECT invocation_id, project_identity, command, mode, outcome, exit_code, "
        "toString(started_at) AS started_at, toString(completed_at) AS completed_at, "
        "duration_ms, selected_node_count, error_message, summary_json, tool_version "
        "FROM `analytics`.`_streambuild_invocations` "
        "WHERE NOT (command = 'audit' AND coalesce(mode, '') = 'scheduled') "
        "ORDER BY started_at DESC LIMIT 100"
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
                        "project",
                        "build",
                        None,
                        "succeeded",
                        0,
                        "2026-08-07 11:00:00.000",
                        "2026-08-07 11:01:00.000",
                        60000,
                        1,
                        None,
                        "{}",
                        "0.26.4",
                    ),
                ),
                column_names=(
                    "invocation_id",
                    "project_identity",
                    "command",
                    "mode",
                    "outcome",
                    "exit_code",
                    "started_at",
                    "completed_at",
                    "duration_ms",
                    "selected_node_count",
                    "error_message",
                    "summary_json",
                    "tool_version",
                ),
            ),
        },
    )

    runs: dict[str, dict[str, object]] = _terminal_runs(
        connection=connection,
        database="analytics",
        limit=100,
        scheduled=False,
    )

    assert runs[test_case.invocation_id]["command"] == test_case.expected_command


@pytest.mark.parametrize(
    "test_case",
    [
        DevRefactorTestCase(
            description="active query exposes normalized progress metrics",
            expected_value={
                "found": True,
                "statementSequence": 4,
                "readRowsPerSecond": 10.0,
                "settings": {"max_threads": "1"},
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_query_when_reading_progress_then_metrics_are_exposed(
    test_case: DevRefactorTestCase,
) -> None:
    payload: dict[str, object] | None = _statement_progress(
        connection=cast(AdapterConnection, StatementProgressConnection()),
        events=[
            {
                "event": "statement_started",
                "statementSequence": 4,
                "stepId": "replay_orders",
                "phase": "replay",
                "queryId": "query-123",
            }
        ],
        observed_at="2026-08-07 12:00:00.000",
    )

    assert payload is not None
    expected: dict[str, object] = cast(dict[str, object], test_case.expected_value)
    assert {key: payload[key] for key in expected} == expected


@pytest.mark.parametrize(
    "test_case",
    [
        RunStatementReadTestCase(
            description="returns the exact persisted statement payload for one sequence",
            invocation_id="inv-1",
            statement_sequence=3,
            row=("replay_orders", "replay", "mutation", "INSERT SELECT 1;", "a", "b"),
            expected_sql="INSERT SELECT 1;",
            expected_step_id="replay_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_persisted_statement_when_reading_run_sql_then_exact_payload_is_returned(
    test_case: RunStatementReadTestCase,
) -> None:
    table_query = (
        "SELECT count() AS present FROM system.tables "
        "WHERE database = 'analytics' AND name = '_streambuild_run_statements'"
    )
    statement_query = (
        "SELECT step_id, phase, intent, sql, toString(sql_sha256) AS sql_sha256, "
        "toString(workflow_sha256) AS workflow_sha256 "
        "FROM `analytics`.`_streambuild_run_statements` FINAL "
        f"WHERE invocation_id = '{test_case.invocation_id}' "
        f"AND statement_sequence = {test_case.statement_sequence} LIMIT 1"
    )
    connection: FakeAdapterConnection = build_fake_state_connection(
        additional_results={
            table_query: AdapterQueryResult(
                column_names=("present",),
                rows=((1,),),
            ),
            statement_query: AdapterQueryResult(
                column_names=(
                    "step_id",
                    "phase",
                    "intent",
                    "sql",
                    "sql_sha256",
                    "workflow_sha256",
                ),
                rows=(test_case.row,),
            ),
        }
    )

    payload: dict[str, object] = read_run_statement(
        connection=connection,
        database="analytics",
        invocation_id=test_case.invocation_id,
        statement_sequence=test_case.statement_sequence,
    )

    assert payload["found"] is True
    assert payload["sql"] == test_case.expected_sql
    assert payload["stepId"] == test_case.expected_step_id


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
            description="active run exposes completed operations and current step",
            expected_value={
                "completedOperationCount": 1,
                "totalStatements": 2,
                "currentStep": "replay_orders",
                "toolVersion": "0.16.4",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_event_stream_when_assembling_run_then_progress_is_exposed(
    test_case: DevRefactorTestCase,
) -> None:
    runs: list[dict[str, object]] = _assemble_runs(
        terminal_by_id={},
        streams={
            "inv-active": [
                {
                    "event": "run_started",
                    "emittedAt": "2026-08-07 11:59:00.000",
                    "command": "build",
                    "totalStatements": 2,
                    "toolVersion": "0.16.4",
                },
                {
                    "event": "statement_started",
                    "emittedAt": "2026-08-07 11:59:10.000",
                    "stepId": "prepare_orders",
                    "statementSequence": 1,
                },
                {
                    "event": "statement_completed",
                    "emittedAt": "2026-08-07 11:59:20.000",
                    "stepId": "prepare_orders",
                    "statementSequence": 1,
                },
                {
                    "event": "statement_started",
                    "emittedAt": "2026-08-07 11:59:30.000",
                    "stepId": "replay_orders",
                    "statementSequence": 2,
                },
                {
                    "event": "run_heartbeat",
                    "emittedAt": "2026-08-07 11:59:40.000",
                    "stepId": None,
                },
            ]
        },
        warehouse_now=_WAREHOUSE_NOW,
        limit=None,
    )

    expected: dict[str, object] = cast(dict[str, object], test_case.expected_value)
    progress: dict[str, object] = {key: runs[0][key] for key in expected}
    assert progress == expected


@pytest.mark.parametrize(
    "test_case",
    [
        DevRefactorTestCase(
            description="active audit cycle exposes partial outcomes",
            expected_value={
                "passed": 1,
                "warning": 0,
                "failed": 0,
                "error": 1,
                "total": 2,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_audit_cycle_when_assembling_run_then_partial_outcomes_are_exposed(
    test_case: DevRefactorTestCase,
) -> None:
    runs: list[dict[str, object]] = _assemble_runs(
        terminal_by_id={},
        streams={
            "audit-cycle": [
                {
                    "event": "run_started",
                    "emittedAt": "2026-08-07 11:59:00.000",
                    "command": "audit",
                    "mode": "scheduled",
                    "totalStatements": 4,
                },
                {
                    "event": "audit_completed",
                    "emittedAt": "2026-08-07 11:59:10.000",
                    "stepId": "fresh_orders",
                    "status": "passed",
                },
                {
                    "event": "audit_completed",
                    "emittedAt": "2026-08-07 11:59:20.000",
                    "stepId": "valid_currency",
                    "status": "error",
                },
            ]
        },
        warehouse_now=_WAREHOUSE_NOW,
        limit=None,
    )

    assert runs[0]["auditSummary"] == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        DevRefactorTestCase(
            description="completed audit cycle exposes durable outcome counts",
            expected_value={
                "passed": 126,
                "warning": 4,
                "failed": 0,
                "error": 53,
                "total": 183,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_completed_audit_cycle_when_reading_summary_then_durable_counts_are_exposed(
    test_case: DevRefactorTestCase,
) -> None:
    summary: dict[str, int] | None = _terminal_audit_summary(
        command="audit",
        mode="scheduled",
        summary_json=(
            '{"scheduled_count":183,"warning_failure_count":4,'
            '"error_failure_count":0,"execution_error_count":53}'
        ),
    )

    assert summary == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        DevRefactorTestCase(
            description="durable audit summary wins over windowed events",
            expected_value={
                "passed": 126,
                "warning": 4,
                "failed": 0,
                "error": 53,
                "total": 183,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_terminal_audit_cycle_when_events_are_windowed_then_durable_summary_wins(
    test_case: DevRefactorTestCase,
) -> None:
    durable_summary: dict[str, int] = cast(dict[str, int], test_case.expected_value)
    runs: list[dict[str, object]] = _assemble_runs(
        terminal_by_id={
            "audit-cycle": {
                "invocationId": "audit-cycle",
                "command": "audit",
                "startedAt": "2026-08-07 11:00:00.000",
                "lastSignalAt": "2026-08-07 11:01:00.000",
                "auditSummary": durable_summary,
            }
        },
        streams={
            "audit-cycle": [
                {
                    "event": "run_started",
                    "emittedAt": "2026-08-07 11:00:00.000",
                    "command": "audit",
                },
                {
                    "event": "audit_completed",
                    "emittedAt": "2026-08-07 11:00:01.000",
                    "stepId": "one-visible-event",
                    "status": "passed",
                },
            ]
        },
        warehouse_now=_WAREHOUSE_NOW,
        limit=None,
    )

    assert runs[0]["auditSummary"] == durable_summary


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
        "(project_identity = 'project' OR endsWith(project_identity, '/project')) AND "
        "target_identity = 'analytics' AND command = 'build' AND mode = 'direct' "
        "AND materialized_outcome IS NOT NULL "
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
            description="project timeout controls presumed failure",
            terminal_outcome=None,
            completed_event_outcome=None,
            signal_age_seconds=90,
            presumed_failed_after_seconds=60,
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
        presumed_failed_after_seconds=test_case.presumed_failed_after_seconds,
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
        "SELECT invocation_id, project_identity, command, mode, outcome, exit_code, "
        "toString(started_at) AS started_at, toString(completed_at) AS completed_at, "
        "duration_ms, selected_node_count, error_message, summary_json, tool_version "
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
                        "project",
                        "build",
                        "direct",
                        "succeeded",
                        0,
                        "2026-01-01 00:00:00.000",
                        "2026-01-01 00:01:00.000",
                        60000,
                        1,
                        None,
                        "{}",
                        "0.7.0",
                    ),
                ),
                column_names=(
                    "invocation_id",
                    "project_identity",
                    "command",
                    "mode",
                    "outcome",
                    "exit_code",
                    "started_at",
                    "completed_at",
                    "duration_ms",
                    "selected_node_count",
                    "error_message",
                    "summary_json",
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
