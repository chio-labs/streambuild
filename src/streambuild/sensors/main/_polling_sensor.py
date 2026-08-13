"""The polling_sensor decorator for authored sensors."""

from __future__ import annotations

from collections.abc import Callable

from streambuild.sensors.constants import DEFAULT_SENSOR_TIMEOUT_SECONDS
from streambuild.sensors.exceptions import SensorError
from streambuild.sensors.models import PollingSensorDeclaration, SensorRetryPolicy
from streambuild.sensors.types import DefaultSensorStatus, SensorFunction


def polling_sensor(
    *,
    minimum_interval_seconds: float,
    name: str | None = None,
    default_status: DefaultSensorStatus = DefaultSensorStatus.STOPPED,
    retry_policy: SensorRetryPolicy | None = None,
    timeout_seconds: float = DEFAULT_SENSOR_TIMEOUT_SECONDS,
) -> Callable[[SensorFunction], PollingSensorDeclaration]:
    """Declare one polling sensor evaluated on a minimum interval from tick start."""

    if minimum_interval_seconds <= 0:
        raise SensorError("polling_sensor minimum_interval_seconds must be positive")
    if timeout_seconds <= 0:
        raise SensorError("polling_sensor timeout_seconds must be positive")

    def decorate(function: SensorFunction) -> PollingSensorDeclaration:
        sensor_name: str = name if name is not None else str(getattr(function, "__name__", ""))
        if not sensor_name:
            raise SensorError("polling_sensor name must not be empty")
        return PollingSensorDeclaration(
            function=function,
            name=sensor_name,
            minimum_interval_seconds=minimum_interval_seconds,
            default_status=DefaultSensorStatus(default_status),
            retry_policy=retry_policy if retry_policy is not None else SensorRetryPolicy(),
            timeout_seconds=timeout_seconds,
        )

    return decorate
