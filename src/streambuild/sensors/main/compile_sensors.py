"""Compile project sensors and providers into one immutable artifact."""

from __future__ import annotations

from pathlib import Path

from streambuild.diagnostics.models import SourceLocation
from streambuild.provider.main.discover_provider_classes import discover_provider_classes
from streambuild.provider.models import DiscoveredProvider
from streambuild.sensors._helpers.dispatch import event_source_for
from streambuild.sensors._helpers.registry import discover_sensor_paths, load_project_sensors
from streambuild.sensors.exceptions import SensorError
from streambuild.sensors.models import (
    CompiledSensors,
    EventSensorDeclaration,
    LoadedSensor,
    SensorRegistry,
)


def compile_sensors(*, project_dir: Path, reserved_names: frozenset[str]) -> CompiledSensors | None:
    """Load, validate, and freeze all authored sensors and providers, or none."""

    sensor_paths: tuple[Path, ...] = discover_sensor_paths(project_dir=project_dir)
    providers: tuple[DiscoveredProvider, ...] = discover_provider_classes(project_dir=project_dir)
    if not sensor_paths and not providers:
        return None
    registry: SensorRegistry = load_project_sensors(
        project_dir=project_dir, sensor_paths=sensor_paths
    )
    for sensor in registry.ordered():
        _validate_sensor(sensor=sensor, reserved_names=reserved_names)
    return CompiledSensors(registry=registry, providers=providers)


def _validate_sensor(*, sensor: LoadedSensor, reserved_names: frozenset[str]) -> None:
    location: SourceLocation = SourceLocation(
        path=sensor.file_path, line=sensor.definition_line, column=1
    )
    if sensor.name in reserved_names:
        raise SensorError(
            f"Sensor name '{sensor.name}' collides with another project resource; "
            "sensor names are globally unique alongside pipelines, models, and audits",
            location=location,
        )
    declaration: object = sensor.declaration
    if isinstance(declaration, EventSensorDeclaration):
        try:
            _ = event_source_for(declaration.event_type)
        except SensorError as error:
            raise SensorError(str(error), location=location) from error
