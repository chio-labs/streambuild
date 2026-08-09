from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedFingerprintTestCase:
    description: str
    settings: tuple[tuple[str, str], ...]
    expected_settings: dict[str, str]
