"""Macros exceptions."""

from streambuild.diagnostics.models import (
    CompilerDiagnostic,
    RelatedDiagnosticLocation,
    SourceLocation,
)
from streambuild.diagnostics.types import DiagnosticPhase, DiagnosticSeverity


class MacroError(ValueError):
    """Raised when macros input or state is invalid."""

    def __init__(
        self,
        message: str,
        *,
        location: SourceLocation | None = None,
        related_locations: tuple[RelatedDiagnosticLocation, ...] = (),
    ) -> None:
        super().__init__(message)
        self.location: SourceLocation | None = location
        self.diagnostic: CompilerDiagnostic = CompilerDiagnostic(
            phase=DiagnosticPhase.COMPILATION,
            severity=DiagnosticSeverity.ERROR,
            code="STB-COMPILE-001",
            message=message,
            location=location,
            related_locations=related_locations,
        )
