"""The event_sensor decorator for authored sensors."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from streambuild.sensors.constants import DEFAULT_SENSOR_TIMEOUT_SECONDS
from streambuild.sensors.exceptions import SensorError
from streambuild.sensors.models import EventSensorDeclaration, SensorRetryPolicy
from streambuild.sensors.types import DefaultSensorStatus, SensorFunction


def event_sensor(
    *,
    on: type,
    name: str | None = None,
    targets: Iterable[str] | None = None,
    triggers: Iterable[str] | None = None,
    default_status: DefaultSensorStatus = DefaultSensorStatus.STOPPED,
    retry_policy: SensorRetryPolicy | None = None,
    timeout_seconds: float = DEFAULT_SENSOR_TIMEOUT_SECONDS,
) -> Callable[[SensorFunction], EventSensorDeclaration]:
    """Declare one durable event sensor reacting to derived warehouse events."""

    if timeout_seconds <= 0:
        raise SensorError("event_sensor timeout_seconds must be positive")

    def decorate(function: SensorFunction) -> EventSensorDeclaration:
        sensor_name: str = name if name is not None else str(getattr(function, "__name__", ""))
        if not sensor_name:
            raise SensorError("event_sensor name must not be empty")
        return EventSensorDeclaration(
            function=function,
            event_type=on,
            name=sensor_name,
            targets=frozenset(targets) if targets is not None else None,
            triggers=frozenset(triggers) if triggers is not None else None,
            default_status=DefaultSensorStatus(default_status),
            retry_policy=retry_policy if retry_policy is not None else SensorRetryPolicy(),
            timeout_seconds=timeout_seconds,
        )

    return decorate
