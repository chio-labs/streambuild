from dataclasses import dataclass, field

from streambuild.events.models import InvocationObservation, NodeResultObservation
from streambuild.executor.auditing.types import QualityResultStatus
from streambuild.sensors.models import (
    LoadedSensor,
    PollingTickState,
    SensorDispatchSummary,
    SensorStreamPosition,
    TickAttemptState,
)
from streambuild.sensors.types import SensorOverrideStatus, SensorTickStatus


@dataclass(frozen=True)
class DispatcherScenarioTestCase:
    description: str
    sensor: LoadedSensor
    expected_tick_statuses: tuple[str, ...]
    expected_advanced_count: int
    expected_summary: SensorDispatchSummary
    checkpoints: dict[tuple[str, str], SensorStreamPosition] = field(default_factory=dict)
    node_results: tuple[NodeResultObservation, ...] = ()
    invocations: tuple[InvocationObservation, ...] = ()
    previous_statuses: dict[str, QualityResultStatus] = field(default_factory=dict)
    attempt_states: dict[tuple[str, str], TickAttemptState] = field(default_factory=dict)
    overrides: dict[str, SensorOverrideStatus] = field(default_factory=dict)
    polling_states: dict[str, PollingTickState] = field(default_factory=dict)
    newest_position: SensorStreamPosition | None = None
    lease_acquired: bool = True


@dataclass(frozen=True)
class DeadLetterActionTestCase:
    description: str
    sensor: LoadedSensor
    node_results: tuple[NodeResultObservation, ...]
    attempt_states: dict[tuple[str, str], TickAttemptState]
    event_id: str
    expected_status: SensorTickStatus
    expected_tick_statuses: tuple[str, ...]
    expected_tick_attempts: tuple[int, ...]
    expected_skip_reason: str | None = None


@dataclass(frozen=True)
class StepRunnerTestCase:
    description: str
    expected_first_value: object
    expected_second_value: object
    expected_call_count: int
