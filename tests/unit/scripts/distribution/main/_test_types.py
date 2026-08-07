from dataclasses import dataclass


@dataclass(frozen=True)
class ValidWheelAssetsTestCase:
    description: str
    archive_names: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class InvalidWheelAssetsTestCase:
    description: str
    archive_names: tuple[str, ...]
    expected_message_fragment: str
