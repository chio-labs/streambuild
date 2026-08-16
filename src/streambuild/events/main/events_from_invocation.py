"""Derive events from one persisted terminal invocation row."""

from __future__ import annotations

from streambuild.events.models import InvocationObservation, RunCompleted
from streambuild.events.types import ObservedCommand


def events_from_invocation(*, row: InvocationObservation) -> tuple[RunCompleted, ...]:
    """Map one invocation row to its derived events, exhaustively by command."""

    try:
        command: ObservedCommand = ObservedCommand(row.command)
    except ValueError:
        return ()
    match command:
        case (
            ObservedCommand.AUDIT
            | ObservedCommand.TEST
            | ObservedCommand.BUILD
            | ObservedCommand.DEPLOYMENT_PROMOTE
            | ObservedCommand.JANITOR
        ):
            return (
                RunCompleted(
                    id=row.invocation_id,
                    command=command,
                    mode=row.mode,
                    outcome=row.outcome,
                    exit_code=row.exit_code,
                    target=row.target_identity,
                    deployment_id=row.deployment_id,
                    selected_node_count=row.selected_node_count,
                    error_message=row.error_message,
                    completed_at=row.completed_at,
                ),
            )
