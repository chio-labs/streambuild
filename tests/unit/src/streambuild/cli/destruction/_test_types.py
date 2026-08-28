from dataclasses import dataclass


@dataclass(frozen=True)
class DestructionParserTestCase:
    description: str
    argv: tuple[str, ...]
    expected_command: str
    expected_target: str
    expected_selectors: tuple[str, ...]
    expected_control_store_url: str | None = None
    expected_include_orphans: bool = False


@dataclass(frozen=True)
class DestructionRejectedOptionTestCase:
    description: str
    command: str
    required_arguments: tuple[str, ...]
    option: str
    expected_exit_code: int
