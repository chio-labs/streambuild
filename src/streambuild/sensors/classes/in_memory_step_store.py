"""Process-local step store for handler unit tests."""

from __future__ import annotations

from streambuild.sensors.models import StepMarker
from streambuild.sensors.types import SensorTickStatus, StepPolicy


class InMemoryStepStore:
    """Dictionary-backed step markers with the persisted-store reduction semantics."""

    def __init__(self) -> None:
        self._markers: dict[str, StepMarker] = {}

    def read_step(self, *, step_key: str) -> StepMarker | None:
        return self._markers.get(step_key)

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
        existing: StepMarker | None = self._markers.get(step_key)
        if existing is not None and existing.status == SensorTickStatus.SUCCEEDED:
            return
        self._markers[step_key] = StepMarker(
            status=str(status), result_json=result_json, attempt=attempt
        )
