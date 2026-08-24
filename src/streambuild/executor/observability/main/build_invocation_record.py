"""Construct one terminal invocation observation."""

from datetime import UTC, datetime
from time import monotonic_ns

from streambuild.adapter.models import AdapterInvocationRecord
from streambuild.cli.build.constants import STREAMBUILD_TOOL_VERSION
from streambuild.executor.observability._helpers.payload import (
    bounded_json,
    complete_json,
    concise_error,
)
from streambuild.executor.observability.main.logical_project_identity import (
    logical_project_identity,
)
from streambuild.executor.observability.models import TerminalInvocation


def build_invocation_record(
    *, started: tuple[str, str, int], terminal: TerminalInvocation
) -> AdapterInvocationRecord:
    """Build one immutable terminal invocation row."""

    completed_at: str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    complete_summary_commands: frozenset[str] = frozenset({"destroy pipelines", "reset target"})
    summary_json: str = (
        complete_json(terminal.summary)
        if terminal.command in complete_summary_commands
        else bounded_json(terminal.summary)
    )
    return AdapterInvocationRecord(
        invocation_id=started[0],
        project_identity=logical_project_identity(project_dir=terminal.project_dir),
        target_identity=terminal.target_identity,
        command=terminal.command,
        mode=terminal.mode,
        outcome=terminal.outcome,
        exit_code=terminal.exit_code,
        materialized_outcome=terminal.materialized_outcome,
        deployment_id=terminal.deployment_id,
        workflow_id=terminal.workflow_id,
        selected_node_count=terminal.selected_node_count,
        started_at=started[1],
        completed_at=completed_at,
        duration_ms=max(0, (monotonic_ns() - started[2]) // 1_000_000),
        error_message=concise_error(terminal.error_message),
        summary_json=summary_json,
        tool_version=STREAMBUILD_TOOL_VERSION,
        artifact_project_dir=str(terminal.project_dir.resolve()),
    )
