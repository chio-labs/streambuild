"""Immutable structured diagnostic models."""

from dataclasses import dataclass
from pathlib import Path

from streambuild.diagnostics.types import DiagnosticPhase, DiagnosticSeverity


@dataclass(frozen=True)
class SourceLocation:
    """One one-based source span."""

    path: Path
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None


@dataclass(frozen=True)
class RelatedDiagnosticLocation:
    """One labeled source span related to a primary diagnostic."""

    label: str
    location: SourceLocation
    message: str | None = None


@dataclass(frozen=True)
class CompilerDiagnostic:
    """One structured compiler or runtime diagnostic."""

    phase: DiagnosticPhase | str
    severity: DiagnosticSeverity | str
    code: str
    message: str
    resource_name: str | None = None
    location: SourceLocation | None = None
    related_locations: tuple[RelatedDiagnosticLocation, ...] = ()
    help: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", DiagnosticPhase(self.phase))
        object.__setattr__(self, "severity", DiagnosticSeverity(self.severity))
