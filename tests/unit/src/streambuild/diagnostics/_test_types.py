from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticTextTestCase:
    description: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosticJsonTestCase:
    description: str
    expected_phase: str
    expected_code: str
    expected_location: tuple[str, int, int, int, int]
    expected_related_label: str


@dataclass(frozen=True)
class RuntimeDiagnosticTestCase:
    description: str
    error_message: str
    expected_fragments: tuple[str, ...]
