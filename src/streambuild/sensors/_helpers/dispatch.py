"""Dispatch helpers: source mapping, status resolution, matching, summarizing."""

from __future__ import annotations

from streambuild.events.models import AuditCompleted, RunCompleted
from streambuild.events.types import SensorEvent
from streambuild.sensors.constants import (
    INVOCATIONS_EVENT_SOURCE,
    NODE_RESULTS_EVENT_SOURCE,
)
from streambuild.sensors.exceptions import SensorError
from streambuild.sensors.models import (
    EventSensorDeclaration,
    LoadedSensor,
    SensorDeliveryOutcome,
    SensorDispatchSummary,
)
from streambuild.sensors.types import (
    DefaultSensorStatus,
    SensorOverrideStatus,
    SensorTickStatus,
)


def event_source_for(event_type: type) -> str:
    """Map one catalog event type to its persisted observation stream."""

    if event_type is AuditCompleted:
        return NODE_RESULTS_EVENT_SOURCE
    if event_type is RunCompleted:
        return INVOCATIONS_EVENT_SOURCE
    raise SensorError(
        f"Unsupported sensor event type '{getattr(event_type, '__name__', event_type)}'; "
        "event sensors react to streambuild.events catalog events"
    )


def effective_sensor_status(
    *, sensor: LoadedSensor, overrides: dict[str, SensorOverrideStatus]
) -> SensorOverrideStatus:
    """Resolve the runtime status: operator override, else declared default."""

    override: SensorOverrideStatus | None = overrides.get(sensor.name)
    if override is not None and override is not SensorOverrideStatus.DECLARED_IN_CODE:
        return override
    if sensor.default_status is DefaultSensorStatus.RUNNING:
        return SensorOverrideStatus.RUNNING
    return SensorOverrideStatus.STOPPED


def matches_sensor(*, declaration: EventSensorDeclaration, event: SensorEvent) -> bool:
    """Match one derived event against the sensor's type, target, and trigger filters."""

    if type(event) is not declaration.event_type:
        return False
    if declaration.targets is not None and event.target not in declaration.targets:
        return False
    if declaration.triggers is not None:
        trigger: object = getattr(event, "trigger", None)
        if trigger is None or str(trigger) not in declaration.triggers:
            return False
    return True


def event_declaration_of(sensor: LoadedSensor) -> EventSensorDeclaration:
    """Return the event declaration or fail when the sensor is not event-driven."""

    declaration: object = sensor.declaration
    if not isinstance(declaration, EventSensorDeclaration):
        raise SensorError(f"Sensor '{sensor.name}' is not an event sensor")
    return declaration


def summarize_outcomes(
    *, outcomes: tuple[SensorDeliveryOutcome, ...], lease_acquired: bool
) -> SensorDispatchSummary:
    """Fold per-delivery outcomes into one dispatch summary."""

    evaluations: tuple[SensorTickStatus, ...] = tuple(
        outcome.evaluation.status for outcome in outcomes if outcome.evaluation is not None
    )
    return SensorDispatchSummary(
        lease_acquired=lease_acquired,
        evaluated=len(evaluations),
        succeeded=sum(1 for status in evaluations if status is SensorTickStatus.SUCCEEDED),
        skipped=sum(1 for status in evaluations if status is SensorTickStatus.SKIPPED),
        failed=sum(1 for status in evaluations if status is SensorTickStatus.FAILED),
        dead_lettered=sum(1 for outcome in outcomes if outcome.dead_lettered),
    )
