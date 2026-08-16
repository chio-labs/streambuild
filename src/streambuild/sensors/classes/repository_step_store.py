"""Durable step store bound to one (sensor, event) against the state repository."""

from __future__ import annotations

from streambuild.adapter.models import AdapterSensorStepRecord
from streambuild.sensors.classes.sensor_state_repository import SensorStateRepository
from streambuild.sensors.models import StepMarker
from streambuild.sensors.types import SensorTickStatus, StepPolicy


class RepositoryStepStore:
    """Persist and reduce step markers through the sensor state repository."""

    def __init__(
        self, *, repository: SensorStateRepository, sensor_name: str, event_id: str
    ) -> None:
        self._repository: SensorStateRepository = repository
        self._sensor_name: str = sensor_name
        self._event_id: str = event_id

    def read_step(self, *, step_key: str) -> StepMarker | None:
        return self._repository.read_step(
            sensor_name=self._sensor_name, event_id=self._event_id, step_key=step_key
        )

    def record_step(
        self,
        *,
        step_key: str,
        policy: StepPolicy,
        status: SensorTickStatus,
        attempt: int,
        result_json: str | None,
        error_message: str | None,
    ) -> None:
        self._repository.record_step(
            step=AdapterSensorStepRecord(
                sensor_name=self._sensor_name,
                event_id=self._event_id,
                step_key=step_key,
                policy=str(policy),
                status=str(status),
                attempt=attempt,
                result_json=result_json,
                error_message=error_message,
            )
        )
