from collections.abc import Callable
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterInvocationRecord, AdapterNodeResultRecord
from streambuild.events.models import AuditCompleted
from streambuild.events.types import SensorEvent
from streambuild.sensors.classes.event_sensor_context import EventSensorContext
from streambuild.sensors.models import (
    EventSensorDeclaration,
    LoadedSensor,
    SensorRegistry,
)
from streambuild.sensors.types import SensorDeclaration, SensorKind


def _raise_boom() -> None:
    raise RuntimeError("boom")


def _noop() -> None:
    return None


_FIRST_CALL_ACTIONS: dict[bool, Callable[[], None]] = {True: _raise_boom, False: _noop}


class RecordingHandler:
    """Capture delivered events and never fail."""

    def __init__(self) -> None:
        self.events: list[AuditCompleted] = []

    def __call__(self, ctx: EventSensorContext[AuditCompleted]) -> None:
        self.events.append(ctx.event)


class FlakyHandler:
    """Fail on the first delivery, succeed afterwards."""

    def __init__(self) -> None:
        self.calls: int = 0
        self.event_ids: list[str] = []

    def __call__(self, ctx: EventSensorContext[SensorEvent]) -> None:
        self.calls += 1
        self.event_ids.append(ctx.event.id)
        _FIRST_CALL_ACTIONS[self.calls == 1]()


class AlwaysFailingHandler:
    """Fail every delivery."""

    def __init__(self) -> None:
        self.calls: int = 0
        self.events: list[AuditCompleted] = []

    def __call__(self, ctx: EventSensorContext[AuditCompleted]) -> None:
        self.calls += 1
        self.events.append(ctx.event)
        raise RuntimeError("poisoned event")


class CountingStepAction:
    """Step body counting its true invocations."""

    def __init__(self) -> None:
        self.calls: int = 0

    def __call__(self) -> object:
        self.calls += 1
        return f"ticket-{self.calls}"


class StepCrashHandler:
    """Run one durable step, then crash on the first attempt only."""

    def __init__(self) -> None:
        self.calls: int = 0
        self.step_action: CountingStepAction = CountingStepAction()
        self.step_values: list[object] = []

    def __call__(self, ctx: EventSensorContext[SensorEvent]) -> None:
        self.calls += 1
        self.step_values.append(ctx.step("jira", self.step_action))
        _FIRST_CALL_ACTIONS[self.calls == 1]()


def build_loaded_sensor(*, declaration: SensorDeclaration, name: str | None = None) -> LoadedSensor:
    kinds: dict[bool, SensorKind] = {True: SensorKind.EVENT, False: SensorKind.POLLING}
    return LoadedSensor(
        name=name or declaration.name,
        kind=kinds[isinstance(declaration, EventSensorDeclaration)],
        declaration=declaration,
        file_path=Path("/project/sensors/quality.py"),
        relative_path=Path("sensors/quality.py"),
        source="def handler(ctx): ...",
        definition_line=1,
        timeout_seconds=declaration.timeout_seconds,
    )


def build_registry(*, sensors: tuple[LoadedSensor, ...]) -> SensorRegistry:
    return SensorRegistry(sensors={sensor.name: sensor for sensor in sensors})


def seed_node_result(
    *,
    connection: AdapterConnection,
    database: str,
    result_id: str,
    status: str,
    completed_at: str,
    target_identity: str,
    binding_key: str = "binding-orders",
    payload_json: str = "{}",
) -> None:
    invocation: AdapterInvocationRecord = AdapterInvocationRecord(
        invocation_id=f"inv-{result_id}",
        project_identity="orders_project",
        target_identity=target_identity,
        command="audit",
        mode=None,
        outcome="succeeded",
        exit_code=0,
        materialized_outcome=None,
        deployment_id=None,
        workflow_id=None,
        selected_node_count=1,
        started_at=completed_at,
        completed_at=completed_at,
        duration_ms=0,
        error_message=None,
        summary_json="{}",
        tool_version="1.2.3",
    )
    node_result: AdapterNodeResultRecord = AdapterNodeResultRecord(
        result_id=result_id,
        invocation_id=invocation.invocation_id,
        node_kind="audit",
        node_name="orders_fresh",
        binding_key=binding_key,
        definition_fingerprint="def-fp",
        execution_fingerprint="exec-fp",
        target_identity=target_identity,
        trigger="scheduled",
        scheduled_for=None,
        cadence_seconds=None,
        warmup_seconds=0,
        status=status,
        severity="error",
        failure_count=1,
        completed_at=completed_at,
        payload_json=payload_json,
        error_message=None,
    )
    rendered: tuple[str, ...] = connection.render_terminal_observations(
        database=database, invocation=invocation, node_results=(node_result,)
    )
    for statement in rendered:
        _ = connection.execute_workflow_sql(statement)
