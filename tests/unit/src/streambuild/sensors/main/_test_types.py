from dataclasses import dataclass


@dataclass(frozen=True)
class CompileSensorsTestCase:
    description: str
    sensor_files: tuple[tuple[str, str], ...]
    provider_files: tuple[tuple[str, str], ...] = ()
    reserved_names: frozenset[str] = frozenset()
    expected_sensor_names: tuple[str, ...] = ()
    expected_provider_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompileSensorsErrorTestCase:
    description: str
    sensor_files: tuple[tuple[str, str], ...]
    reserved_names: frozenset[str]
    expected_error_fragment: str
