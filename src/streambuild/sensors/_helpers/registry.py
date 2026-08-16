"""Load authored sensor declarations from project sensors/ modules."""

from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from streambuild.diagnostics.models import RelatedDiagnosticLocation, SourceLocation
from streambuild.sensors.exceptions import SensorError
from streambuild.sensors.models import (
    EventSensorDeclaration,
    LoadedSensor,
    PollingSensorDeclaration,
    SensorRegistry,
)
from streambuild.sensors.types import SensorDeclaration, SensorKind

_PYTHON_INIT_MODULE_STEM: str = "__init__"


def load_project_sensors(*, project_dir: Path, sensor_paths: tuple[Path, ...]) -> SensorRegistry:
    """Load one deterministic registry from project sensor modules."""

    loaded_sensors: dict[str, LoadedSensor] = {}
    for file_path in sensor_paths:
        module: ModuleType = _load_sensor_module(file_path=file_path, project_dir=project_dir)
        for loaded_sensor in _load_sensors_from_module(
            module=module, file_path=file_path, project_dir=project_dir
        ):
            existing: LoadedSensor | None = loaded_sensors.get(loaded_sensor.name)
            if existing is not None:
                raise SensorError(
                    f"Sensor name collision for '{loaded_sensor.name}' in "
                    f"'{loaded_sensor.file_path}' and '{existing.file_path}'",
                    location=_definition_location(loaded_sensor),
                    related_locations=(
                        RelatedDiagnosticLocation(
                            label="first sensor definition",
                            location=_definition_location(existing),
                        ),
                    ),
                )
            loaded_sensors[loaded_sensor.name] = loaded_sensor
    return SensorRegistry(sensors=loaded_sensors)


def discover_sensor_paths(*, project_dir: Path) -> tuple[Path, ...]:
    """List public sensor module paths in stable order."""

    sensors_root: Path = project_dir / "sensors"
    if not sensors_root.is_dir():
        return ()
    return tuple(
        path
        for path in sorted(sensors_root.rglob("*.py"))
        if _is_public_sensor_file(path=path, project_dir=project_dir)
    )


def _is_public_sensor_file(*, path: Path, project_dir: Path) -> bool:
    relative_path: Path = path.relative_to(project_dir)
    return path.stem != _PYTHON_INIT_MODULE_STEM and not any(
        part.startswith("_") for part in relative_path.parts
    )


def _load_sensor_module(*, file_path: Path, project_dir: Path) -> ModuleType:
    module_name: str = "streambuild_project_sensors_" + "_".join(
        file_path.relative_to(project_dir).with_suffix("").parts
    )
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise SensorError(f"Could not load sensor file {file_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    old_path: list[str] = list(sys.path)
    sys.path.insert(0, str(project_dir))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except SyntaxError as error:
        raise SensorError(
            f"Failed to load {file_path}: {error}",
            location=SourceLocation(
                path=file_path,
                line=error.lineno or 1,
                column=error.offset or 1,
            ),
        ) from error
    except SensorError:
        raise
    except Exception as error:
        raise SensorError(
            f"Failed to load {file_path}: {error}",
            location=SourceLocation(
                path=file_path,
                line=_sensor_exception_line(error=error, file_path=file_path),
                column=1,
            ),
        ) from error
    finally:
        sys.path = old_path
    return module


def _load_sensors_from_module(
    *, module: ModuleType, file_path: Path, project_dir: Path
) -> tuple[LoadedSensor, ...]:
    source: str = file_path.read_text(encoding="utf-8")
    loaded_sensors: list[LoadedSensor] = []
    for _, member in inspect.getmembers(module, _is_sensor_declaration):
        declaration: SensorDeclaration = member
        if declaration.function.__module__ != module.__name__:
            continue
        loaded_sensors.append(
            LoadedSensor(
                name=declaration.name,
                kind=_declaration_kind(declaration),
                declaration=declaration,
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                source=source,
                definition_line=declaration.function.__code__.co_firstlineno,
                description=_sensor_description(declaration.function),
                timeout_seconds=declaration.timeout_seconds,
            )
        )
    return tuple(loaded_sensors)


def _is_sensor_declaration(member: object) -> bool:
    return isinstance(member, EventSensorDeclaration | PollingSensorDeclaration)


def _declaration_kind(declaration: SensorDeclaration) -> SensorKind:
    if isinstance(declaration, EventSensorDeclaration):
        return SensorKind.EVENT
    return SensorKind.POLLING


def _sensor_description(function: object) -> str | None:
    docstring: str | None = inspect.getdoc(function)
    if docstring is None:
        return None
    first_paragraph: str = docstring.split("\n\n")[0].strip()
    return first_paragraph or None


def _definition_location(sensor: LoadedSensor) -> SourceLocation:
    return SourceLocation(path=sensor.file_path, line=sensor.definition_line, column=1)


def _sensor_exception_line(*, error: Exception, file_path: Path) -> int:
    for frame in reversed(traceback.extract_tb(error.__traceback__)):
        if Path(frame.filename) == file_path:
            return frame.lineno or 1
    return 1
