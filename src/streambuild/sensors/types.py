"""Closed sensor vocabulary, shared aliases, and storage protocols."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from streambuild.sensors.models import (
        EventSensorDeclaration,
        PollingSensorDeclaration,
        StepMarker,
    )

type SensorFunction = Callable[..., object]
type SensorDeclaration = EventSensorDeclaration | PollingSensorDeclaration


class SensorKind(StrEnum):
    """Kinds of authored sensors."""

    EVENT = "event"
    POLLING = "polling"


class DefaultSensorStatus(StrEnum):
    """Authored default sensor status declared in code."""

    RUNNING = "running"
    STOPPED = "stopped"


class SensorOverrideStatus(StrEnum):
    """Runtime override state persisted by operator actions."""

    RUNNING = "running"
    STOPPED = "stopped"
    DECLARED_IN_CODE = "declared_in_code"


class SensorTickStatus(StrEnum):
    """Persisted status of one sensor tick attempt."""

    STARTED = "started"
    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class StepPolicy(StrEnum):
    """Durable step re-execution policy."""

    AT_LEAST_ONCE = "at_least_once"
    AT_MOST_ONCE = "at_most_once"


class SensorStepStore(Protocol):
    """Persisted step marker storage keyed by (sensor, event, step)."""

    def read_step(self, *, step_key: str) -> StepMarker | None:
        """Return the reduced marker state for one step, if any."""
        ...

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
        """Append one step marker row."""
        ...
