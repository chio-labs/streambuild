"""Serialize sensor definitions, ticks, and dead letters for the UI."""

from __future__ import annotations

from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.sensors.classes.sensor_state_repository import SensorStateRepository
from streambuild.sensors.main.resolve_effective_sensor_status import (
    resolve_effective_sensor_status,
)
from streambuild.sensors.models import (
    EventSensorDeclaration,
    LoadedSensor,
    PollingSensorDeclaration,
    SensorTickView,
)
from streambuild.sensors.types import SensorOverrideStatus


def build_sensors_payload(
    *,
    analysis: CompileAnalysis,
    repository: SensorStateRepository | None,
    health: dict[str, object],
) -> dict[str, object]:
    """List compiled sensors with effective statuses and their latest tick."""

    sensors: tuple[LoadedSensor, ...] = (
        () if analysis.sensors is None else analysis.sensors.registry.ordered()
    )
    overrides: dict[str, SensorOverrideStatus] = {}
    dead_letters: tuple[SensorTickView, ...] = ()
    if repository is not None and sensors:
        repository.ensure_ready()
        overrides = repository.override_statuses()
        dead_letters = repository.list_dead_letters()
    return {
        "sensors": [
            _sensor_payload(sensor=sensor, overrides=overrides, repository=repository)
            for sensor in sensors
        ],
        "deadLetterCount": len(dead_letters),
        "health": health,
    }


def build_sensor_ticks_payload(
    *, repository: SensorStateRepository | None, sensor_name: str, limit: int
) -> dict[str, object]:
    """List recent ticks for one sensor, newest first."""

    if repository is None:
        return {"sensorName": sensor_name, "ticks": []}
    repository.ensure_ready()
    ticks: tuple[SensorTickView, ...] = repository.list_ticks(sensor_name=sensor_name, limit=limit)
    return {
        "sensorName": sensor_name,
        "ticks": [_tick_payload(tick=tick) for tick in ticks],
    }


def build_dead_letters_payload(*, repository: SensorStateRepository | None) -> dict[str, object]:
    """List unresolved dead-lettered events across all sensors."""

    if repository is None:
        return {"deadLetters": []}
    repository.ensure_ready()
    return {"deadLetters": [_tick_payload(tick=tick) for tick in repository.list_dead_letters()]}


def _sensor_payload(
    *,
    sensor: LoadedSensor,
    overrides: dict[str, SensorOverrideStatus],
    repository: SensorStateRepository | None,
) -> dict[str, object]:
    declaration: object = sensor.declaration
    latest: tuple[SensorTickView, ...] = (
        () if repository is None else repository.list_ticks(sensor_name=sensor.name, limit=1)
    )
    payload: dict[str, object] = {
        "name": sensor.name,
        "kind": str(sensor.kind),
        "description": sensor.description,
        "file": sensor.relative_path.as_posix(),
        "fingerprint": sensor.identity_fingerprint,
        "defaultStatus": str(sensor.default_status),
        "effectiveStatus": str(resolve_effective_sensor_status(sensor=sensor, overrides=overrides)),
        "override": _override_value(sensor=sensor, overrides=overrides),
        "retryPolicy": {
            "maxAttempts": sensor.retry_policy.max_attempts,
            "backoffSeconds": sensor.retry_policy.backoff_seconds,
        },
        "timeoutSeconds": sensor.timeout_seconds,
        "lastTick": _tick_payload(tick=latest[-1]) if latest else None,
    }
    if isinstance(declaration, EventSensorDeclaration):
        payload["eventType"] = declaration.event_type.__name__
        payload["targets"] = None if declaration.targets is None else sorted(declaration.targets)
        payload["triggers"] = None if declaration.triggers is None else sorted(declaration.triggers)
    if isinstance(declaration, PollingSensorDeclaration):
        payload["minimumIntervalSeconds"] = declaration.minimum_interval_seconds
    return payload


def _override_value(
    *, sensor: LoadedSensor, overrides: dict[str, SensorOverrideStatus]
) -> str | None:
    override: SensorOverrideStatus | None = overrides.get(sensor.name)
    if override is None or override is SensorOverrideStatus.DECLARED_IN_CODE:
        return None
    return str(override)


def _tick_payload(*, tick: SensorTickView) -> dict[str, object]:
    return {
        "tickId": tick.tick_id,
        "sensorName": tick.sensor_name,
        "definitionFingerprint": tick.definition_fingerprint,
        "kind": tick.kind,
        "eventId": tick.event_id,
        "eventKind": tick.event_kind,
        "attempt": tick.attempt,
        "status": tick.status,
        "startedAt": tick.started_at,
        "completedAt": tick.completed_at,
        "errorMessage": tick.error_message,
        "skipReason": tick.skip_reason,
        "cursor": tick.cursor,
    }
