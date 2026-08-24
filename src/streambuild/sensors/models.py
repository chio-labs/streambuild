"""Authored sensor declarations and the loaded sensor registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

from streambuild.events.types import SensorEvent
from streambuild.provider.models import DiscoveredProvider
from streambuild.sensors.constants import DEFAULT_SENSOR_TIMEOUT_SECONDS
from streambuild.sensors.exceptions import SensorError
from streambuild.sensors.types import (
    DefaultSensorStatus,
    SensorDeclaration,
    SensorFunction,
    SensorKind,
    SensorTickStatus,
)


@dataclass(frozen=True)
class SensorRetryPolicy:
    """Bounded re-attempt policy for failed event sensor ticks."""

    max_attempts: int = 1
    backoff_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise SensorError("SensorRetryPolicy.max_attempts must be at least 1")
        if self.backoff_seconds < 0:
            raise SensorError("SensorRetryPolicy.backoff_seconds must not be negative")


@dataclass(frozen=True)
class SkipReason:
    """Explicit handler decision to skip one event with a recorded reason."""

    reason: str


@dataclass(frozen=True)
class PollingSensorResult:
    """Terminal result of one polling sensor tick."""

    cursor: str | None = None


@dataclass(frozen=True)
class EventSensorDeclaration:
    """One authored event sensor produced by the event_sensor decorator."""

    function: SensorFunction
    event_type: type
    name: str
    targets: frozenset[str] | None
    triggers: frozenset[str] | None
    maximum_event_age_seconds: float | None
    default_status: DefaultSensorStatus
    retry_policy: SensorRetryPolicy
    timeout_seconds: float

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self.function(*args, **kwargs)


@dataclass(frozen=True)
class PollingSensorDeclaration:
    """One authored polling sensor produced by the polling_sensor decorator."""

    function: SensorFunction
    name: str
    minimum_interval_seconds: float
    default_status: DefaultSensorStatus
    retry_policy: SensorRetryPolicy
    timeout_seconds: float

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self.function(*args, **kwargs)


@dataclass(frozen=True)
class LoadedSensor:
    """One registered authored sensor with retained source identity."""

    name: str
    kind: SensorKind
    declaration: SensorDeclaration
    file_path: Path
    relative_path: Path
    source: str
    definition_line: int
    description: str | None = None
    timeout_seconds: float = DEFAULT_SENSOR_TIMEOUT_SECONDS

    @property
    def identity_fingerprint(self) -> str:
        """Fingerprint the sensor identity and retained implementation source."""

        payload: str = f"{self.name}\0{self.relative_path.as_posix()}\0{self.source}"
        return sha256(payload.encode("utf-8")).hexdigest()

    @property
    def default_status(self) -> DefaultSensorStatus:
        return self.declaration.default_status

    @property
    def retry_policy(self) -> SensorRetryPolicy:
        return self.declaration.retry_policy


@dataclass(frozen=True)
class CompiledSensors:
    """Compiled project automation: loaded sensors plus discovered providers."""

    registry: SensorRegistry
    providers: tuple[DiscoveredProvider, ...] = ()


@dataclass(frozen=True)
class SensorStreamPosition:
    """One (completed_at, id) position in an ordered observation stream."""

    completed_at: str
    result_id: str


@dataclass(frozen=True)
class StepMarker:
    """Reduced durable-step state for one (sensor, event, key)."""

    status: str
    result_json: str | None
    attempt: int


@dataclass(frozen=True)
class TickAttemptState:
    """Reduced tick history for one (sensor, event)."""

    failed_attempts: int
    last_failed_at: str | None
    last_error_message: str | None
    resolved: bool


@dataclass(frozen=True)
class SensorTickView:
    """One reduced tick with its terminal state preferred over started rows."""

    tick_id: str
    sensor_name: str
    definition_fingerprint: str
    kind: str
    event_id: str | None
    event_kind: str | None
    attempt: int
    status: str
    started_at: str
    completed_at: str | None
    error_message: str | None
    skip_reason: str | None
    cursor: str | None


@dataclass(frozen=True)
class PollingTickState:
    """Latest polling tick timing and cursor for one sensor."""

    last_started_at: str | None
    last_success_at: str | None
    cursor: str | None


@dataclass(frozen=True)
class SensorEvaluation:
    """Terminal outcome of one isolated sensor handler invocation."""

    status: SensorTickStatus
    skip_reason: str | None = None
    error_message: str | None = None
    cursor: str | None = None


@dataclass(frozen=True)
class SensorDeliveryOutcome:
    """Resolution of one matched event delivery within a dispatch pass."""

    resolved: bool
    evaluation: SensorEvaluation | None = None
    dead_lettered: bool = False


@dataclass(frozen=True)
class SensorEventDelivery:
    """Events derived from one positioned observation row."""

    position: SensorStreamPosition
    events: tuple[SensorEvent, ...]


@dataclass(frozen=True)
class SensorDispatchSummary:
    """Counters describing one dispatch pass."""

    lease_acquired: bool = True
    evaluated: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    dead_lettered: int = 0


@dataclass(frozen=True)
class SensorRegistry:
    """Deterministic name-keyed registry of loaded project sensors."""

    sensors: Mapping[str, LoadedSensor] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sensors", MappingProxyType(dict(self.sensors)))

    def ordered(self) -> tuple[LoadedSensor, ...]:
        return tuple(self.sensors[name] for name in sorted(self.sensors))
