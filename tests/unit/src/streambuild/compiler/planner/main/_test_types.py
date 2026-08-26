from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedFingerprintTestCase:
    description: str
    settings: tuple[tuple[str, str], ...]
    expected_settings: dict[str, str]


@dataclass(frozen=True)
class MaterializedViewSchedulingTestCase:
    description: str
    expected_refresh: str | None
    expected_append: bool
