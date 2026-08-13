"""Resolve one sensor's runtime status from overrides and its declared default."""

from __future__ import annotations

from streambuild.sensors._helpers.dispatch import effective_sensor_status
from streambuild.sensors.models import LoadedSensor
from streambuild.sensors.types import SensorOverrideStatus


def resolve_effective_sensor_status(
    *, sensor: LoadedSensor, overrides: dict[str, SensorOverrideStatus]
) -> SensorOverrideStatus:
    """Operator override wins unless it defers back to the declared default."""

    return effective_sensor_status(sensor=sensor, overrides=overrides)
