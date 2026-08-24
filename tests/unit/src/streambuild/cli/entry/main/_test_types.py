from dataclasses import dataclass


@dataclass(frozen=True)
class DestructionTtyTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_error_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DestructionDispatchTestCase:
    description: str
    argv: tuple[str, ...]
    expected_operation: str
    expected_selected_target: str
    expected_selectors: tuple[str, ...]
    expected_control_store_url: str
    expected_cli_variables: tuple[tuple[str, object], ...]
    expected_exit_code: int
