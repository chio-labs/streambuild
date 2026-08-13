"""React to persisted audit results; events are derived, never emitted.

Sensors run at least once per event; handlers should tolerate re-execution.
`ctx.event.id` is the idempotency key; use `ctx.step()` to make re-runs resume
instead of redo.
"""

from providers.slack import QualitySlack

from streambuild.events import AuditCompleted, AuditTransition
from streambuild.sensors import (
    DefaultSensorStatus,
    EventSensorContext,
    SensorRetryPolicy,
    event_sensor,
)


@event_sensor(
    on=AuditCompleted,
    default_status=DefaultSensorStatus.STOPPED,
    retry_policy=SensorRetryPolicy(max_attempts=3, backoff_seconds=30),
)
def quality_alerts(ctx: EventSensorContext[AuditCompleted], quality_slack: QualitySlack) -> None:
    """Alert Slack when an audit newly fails or recovers."""

    event = ctx.event
    if event.transition not in {AuditTransition.NEW_FAILURE, AuditTransition.RECOVERED}:
        return
    message = ctx.step(
        "compose",
        lambda: f"{event.audit_name}: {event.transition} on {event.target}",
    )
    ctx.step("slack", lambda: quality_slack.send(str(message)))
