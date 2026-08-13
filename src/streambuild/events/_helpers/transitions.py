"""Audit status transition computation against the previous persisted result."""

from __future__ import annotations

from streambuild.events.types import AuditTransition
from streambuild.executor.auditing.types import QualityResultStatus


def compute_audit_transition(
    *, status: QualityResultStatus, previous_status: QualityResultStatus | None
) -> AuditTransition:
    """Compute the transition of one terminal audit status against the prior result."""

    failing: bool = is_failing_status(status)
    previously_failing: bool = previous_status is not None and is_failing_status(previous_status)
    if failing and previously_failing:
        return AuditTransition.STILL_FAILING
    if failing:
        return AuditTransition.NEW_FAILURE
    if previously_failing:
        return AuditTransition.RECOVERED
    return AuditTransition.STILL_PASSING


def is_failing_status(status: QualityResultStatus) -> bool:
    """Classify one terminal status; warnings and deferrals never count as failures."""

    match status:
        case QualityResultStatus.FAILED | QualityResultStatus.ERROR:
            return True
        case (
            QualityResultStatus.PASSED | QualityResultStatus.WARNING | QualityResultStatus.DEFERRED
        ):
            return False
