"""Derive events from one persisted quality node result row."""

from __future__ import annotations

from streambuild.compiler.quality.types import QualityNodeKind
from streambuild.events._helpers.transitions import compute_audit_transition
from streambuild.events.models import AuditCompleted, NodeResultObservation
from streambuild.executor.auditing.types import QualityResultStatus


def events_from_node_result(
    *, row: NodeResultObservation, previous_status: QualityResultStatus | None, target: str
) -> tuple[AuditCompleted, ...]:
    """Map one node result row to its derived events, exhaustively by node kind."""

    match row.node_kind:
        case QualityNodeKind.TEST:
            return ()
        case QualityNodeKind.AUDIT:
            return _audit_events(row=row, previous_status=previous_status, target=target)


def _audit_events(
    *, row: NodeResultObservation, previous_status: QualityResultStatus | None, target: str
) -> tuple[AuditCompleted, ...]:
    match row.status:
        case QualityResultStatus.DEFERRED:
            return ()
        case (
            QualityResultStatus.PASSED
            | QualityResultStatus.WARNING
            | QualityResultStatus.FAILED
            | QualityResultStatus.ERROR
        ):
            return (
                AuditCompleted(
                    id=row.result_id,
                    audit_name=row.node_name,
                    status=row.status,
                    previous_status=previous_status,
                    transition=compute_audit_transition(
                        status=row.status, previous_status=previous_status
                    ),
                    severity=row.severity,
                    failure_count=row.failure_count,
                    target=target,
                    trigger=row.trigger,
                    completed_at=row.completed_at,
                    binding_key=row.binding_key,
                    invocation_id=row.invocation_id,
                    scheduled_for=row.scheduled_for,
                    error_message=row.error_message,
                ),
            )
