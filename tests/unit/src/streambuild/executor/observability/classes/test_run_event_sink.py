import io
import json
import time
from typing import cast

import pytest

from streambuild.cli.build.constants import STREAMBUILD_TOOL_VERSION
from streambuild.executor.observability.classes.run_event_sink import RunEventSink
from streambuild.executor.observability.constants import RUN_DISPLAY_COMMAND_ENV_VAR
from streambuild.executor.observability.models import RunStartupTimings
from tests.unit.src.streambuild.executor.observability.classes._test_types import (
    RunEventDisplayCommandTestCase,
    RunEventHeartbeatTestCase,
    RunEventScopeTestCase,
    RunEventSinkTestCase,
    RunEventStartupTimingsTestCase,
)
from tests.unit.src.streambuild.executor.observability.classes.helpers import (
    RunEventRecordingConnection,
    build_replay_statement,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RunEventSinkTestCase(
            description="narrates a run as ordered JSONL lines and durable inserts",
            expected_event_kinds=(
                "run_started",
                "statement_started",
                "statement_completed",
                "run_completed",
            ),
            expected_sequences=(1, 2, 3, 4),
            expected_persisted_markers=(
                "INSERT_RUN_EVENT analytics run_started 1;",
                "INSERT_RUN_EVENT analytics statement_started 2;",
                "INSERT_RUN_EVENT analytics statement_completed 3;",
                "INSERT_RUN_EVENT analytics run_completed 4;",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_one_run_when_emitting_then_streams_jsonl_and_persists_rows(
    test_case: RunEventSinkTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection: RunEventRecordingConnection = RunEventRecordingConnection()
    stream: io.StringIO = io.StringIO()
    sink: RunEventSink = RunEventSink(
        connection=connection,
        database="analytics",
        invocation_id="inv-1",
        jsonl_stream=stream,
    )

    monkeypatch.setenv(
        RUN_DISPLAY_COMMAND_ENV_VAR,
        "stb build --target test --select orders --start-time 2026-08-09T09:00:00Z",
    )
    sink.run_started(
        command="build",
        mode="direct",
        total_statements=1,
        selected_node_count=1,
        selectors=("orders",),
        start_time="2026-08-09T09:00:00Z",
    )
    sink.statement_started(build_replay_statement())
    sink.statement_completed(
        statement=build_replay_statement(), error_message=None, written_rows=42, elapsed_ms=5
    )
    sink.run_completed(outcome="succeeded", exit_code=0, error_message=None)

    lines: list[dict] = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert tuple(line["event"] for line in lines) == test_case.expected_event_kinds
    assert tuple(line["sequence"] for line in lines) == test_case.expected_sequences
    assert lines[2]["writtenRows"] == 42
    assert lines[1]["stepId"] == "replay_orders"
    assert lines[0]["command"] == "build"
    assert lines[0]["displayCommand"] == (
        "stb build --target test --select orders --start-time 2026-08-09T09:00:00Z"
    )
    assert lines[0]["toolVersion"] == STREAMBUILD_TOOL_VERSION
    assert lines[0]["selectors"] == ["orders"]
    assert lines[0]["startTime"] == "2026-08-09T09:00:00Z"
    assert all(line["invocationId"] == "inv-1" for line in lines)
    assert tuple(connection.statements) == test_case.expected_persisted_markers


@pytest.mark.parametrize(
    "test_case",
    [
        RunEventSinkTestCase(
            description="scheduled audit emits live start and completion progress",
            expected_event_kinds=(
                "run_started",
                "audit_started",
                "audit_completed",
                "run_completed",
            ),
            expected_sequences=(1, 2, 3, 4),
            expected_persisted_markers=(
                "INSERT_RUN_EVENT analytics run_started 1;",
                "INSERT_RUN_EVENT analytics audit_started 2;",
                "INSERT_RUN_EVENT analytics audit_completed 3;",
                "INSERT_RUN_EVENT analytics run_completed 4;",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scheduled_audit_when_emitting_then_run_progress_is_durable(
    test_case: RunEventSinkTestCase,
) -> None:
    connection: RunEventRecordingConnection = RunEventRecordingConnection()
    stream: io.StringIO = io.StringIO()
    sink: RunEventSink = RunEventSink(
        connection=connection,
        database="analytics",
        invocation_id="inv-scheduled",
        jsonl_stream=stream,
    )

    sink.run_started(command="audit", mode="scheduled", total_statements=1, selected_node_count=1)
    sink.audit_started(name="orders are valid")
    sink.audit_completed(
        name="orders are valid",
        status="passed",
        failure_count=0,
        error_message=None,
    )
    sink.run_completed(outcome="succeeded", exit_code=0, error_message=None)

    lines: list[dict] = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert tuple(line["event"] for line in lines) == test_case.expected_event_kinds
    assert tuple(line["sequence"] for line in lines) == test_case.expected_sequences
    assert lines[1]["stepId"] == "orders are valid"
    assert tuple(connection.statements) == test_case.expected_persisted_markers


@pytest.mark.parametrize(
    "test_case",
    [
        RunEventDisplayCommandTestCase(
            description="child build inherits its display command from the environment",
            command="build",
            environment_command="stb build --select orders",
            explicit_command=None,
            expected_command="stb build --select orders",
        ),
        RunEventDisplayCommandTestCase(
            description="in-process operation supplies its exact display command explicitly",
            command="deployment promote",
            environment_command="stb build --select unrelated",
            explicit_command="stb deployment promote deployment-1",
            expected_command="stb deployment promote deployment-1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_display_command_source_when_starting_run_then_exact_command_is_emitted(
    test_case: RunEventDisplayCommandTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: io.StringIO = io.StringIO()
    sink: RunEventSink = RunEventSink(
        connection=RunEventRecordingConnection(),
        database="analytics",
        invocation_id="inv-display",
        jsonl_stream=stream,
    )
    monkeypatch.setenv(RUN_DISPLAY_COMMAND_ENV_VAR, test_case.environment_command)

    sink.run_started(
        command=test_case.command,
        display_command=test_case.explicit_command,
        mode="virtual_environment",
        total_statements=0,
        selected_node_count=0,
    )
    sink.run_completed(outcome="succeeded", exit_code=0, error_message=None)

    started: dict = json.loads(stream.getvalue().splitlines()[0])
    assert started["command"] == test_case.command
    assert started["displayCommand"] == test_case.expected_command


@pytest.mark.parametrize(
    "test_case",
    [
        RunEventScopeTestCase(
            description="persists exact executed and prerequisite logical identities",
            expected_executed_logical_ids=("model:order_items_v2", "model:daily/revenue"),
            expected_context_logical_ids=("source:order_events_v1",),
        ),
        RunEventScopeTestCase(
            description="persists a complete scope beyond the diagnostic payload bound",
            expected_executed_logical_ids=tuple(
                f"model:long_exact_model_identifier_{index:04d}" for index in range(500)
            ),
            expected_context_logical_ids=("source:order_events_v1",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_authoritative_scope_when_starting_run_then_exact_logical_identities_are_emitted(
    test_case: RunEventScopeTestCase,
) -> None:
    stream: io.StringIO = io.StringIO()
    connection: RunEventRecordingConnection = RunEventRecordingConnection()
    sink: RunEventSink = RunEventSink(
        connection=connection,
        database="analytics",
        invocation_id="inv-scope",
        jsonl_stream=stream,
    )

    sink.run_started(
        command="build",
        mode="direct",
        total_statements=1,
        selected_node_count=len(test_case.expected_executed_logical_ids),
        executed_logical_ids=test_case.expected_executed_logical_ids,
        context_logical_ids=test_case.expected_context_logical_ids,
    )
    sink.run_completed(outcome="succeeded", exit_code=0, error_message=None)

    started: dict = json.loads(stream.getvalue().splitlines()[0])
    persisted_started: dict = json.loads(connection.run_events[0].payload_json)
    assert started["executedLogicalIds"] == list(test_case.expected_executed_logical_ids)
    assert started["contextLogicalIds"] == list(test_case.expected_context_logical_ids)
    assert persisted_started["executedLogicalIds"] == list(test_case.expected_executed_logical_ids)
    assert persisted_started["contextLogicalIds"] == list(test_case.expected_context_logical_ids)


@pytest.mark.parametrize(
    "test_case",
    [
        RunEventStartupTimingsTestCase(
            description="pre-execution phases retain their measured durations",
            compile_ms=420,
            observability_ms=30,
            planning_ms=2050,
            expected_total_ms=2500,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_startup_timings_when_starting_run_then_phase_breakdown_is_emitted(
    test_case: RunEventStartupTimingsTestCase,
) -> None:
    stream: io.StringIO = io.StringIO()
    sink: RunEventSink = RunEventSink(
        connection=RunEventRecordingConnection(),
        database="analytics",
        invocation_id="inv-timings",
        jsonl_stream=stream,
    )

    sink.run_started(
        command="build",
        mode="direct",
        total_statements=1,
        selected_node_count=1,
        startup_timings=RunStartupTimings(
            compile_ms=test_case.compile_ms,
            observability_ms=test_case.observability_ms,
            planning_ms=test_case.planning_ms,
        ),
    )
    sink.run_completed(outcome="succeeded", exit_code=0, error_message=None)

    started: dict[str, object] = json.loads(stream.getvalue().splitlines()[0])
    timings: dict[str, int] = cast(dict[str, int], started["startupTimings"])
    assert timings == {
        "compileMs": test_case.compile_ms,
        "observabilityMs": test_case.observability_ms,
        "planningMs": test_case.planning_ms,
        "totalMs": test_case.expected_total_ms,
    }


@pytest.mark.parametrize(
    "test_case",
    [
        RunEventHeartbeatTestCase(
            description="heartbeat continues while no workflow statement completes",
            expected_event_kind="run_heartbeat",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_long_statement_when_sink_is_active_then_timer_emits_heartbeats(
    test_case: RunEventHeartbeatTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "streambuild.executor.observability.classes.run_event_sink.HEARTBEAT_INTERVAL_SECONDS",
        0.01,
    )
    connection: RunEventRecordingConnection = RunEventRecordingConnection()
    stream: io.StringIO = io.StringIO()
    sink: RunEventSink = RunEventSink(
        connection=connection,
        database="analytics",
        invocation_id="inv-heartbeat",
        jsonl_stream=stream,
    )

    sink.run_started(command="build", mode="direct", total_statements=1, selected_node_count=1)
    time.sleep(0.03)
    sink.run_completed(outcome="succeeded", exit_code=0, error_message=None)

    lines: list[dict] = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert test_case.expected_event_kind in tuple(line["event"] for line in lines)
