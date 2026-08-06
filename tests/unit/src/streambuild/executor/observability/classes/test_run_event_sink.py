import io
import json

import pytest

from streambuild.executor.observability.classes.run_event_sink import RunEventSink
from tests.unit.src.streambuild.executor.observability.classes._test_types import (
    RunEventSinkTestCase,
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
) -> None:
    connection: RunEventRecordingConnection = RunEventRecordingConnection()
    stream: io.StringIO = io.StringIO()
    sink: RunEventSink = RunEventSink(
        connection=connection,
        database="analytics",
        invocation_id="inv-1",
        jsonl_stream=stream,
    )

    sink.run_started(command="build", total_statements=1, selected_node_count=1)
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
    assert all(line["invocationId"] == "inv-1" for line in lines)
    assert tuple(connection.statements) == test_case.expected_persisted_markers
