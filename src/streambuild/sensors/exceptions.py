"""Sensor exceptions."""

from __future__ import annotations

from streambuild.diagnostics.models import (
    CompilerDiagnostic,
    RelatedDiagnosticLocation,
    SourceLocation,
)
from streambuild.diagnostics.types import DiagnosticPhase, DiagnosticSeverity


class SensorError(ValueError):
    """Raised when sensor definitions or project sensor state is invalid."""

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


class SensorStepError(RuntimeError):
    """Raised when a durable step cannot run or return a memoized result."""


class SensorEvaluationTimeoutError(RuntimeError):
    """Raised when one sensor evaluation exceeds its timeout."""
