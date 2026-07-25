from dataclasses import dataclass


@dataclass(frozen=True)
class CliAuditSelectionTestCase:
    description: str
    selectors: tuple[str, ...]
    audit_model_names: tuple[tuple[str, ...], ...]
    expected_selected_indexes: tuple[int, ...]


@dataclass(frozen=True)
class CliAuditSelectionErrorTestCase:
    description: str
    selectors: tuple[str, ...]
    expected_error_fragment: str
