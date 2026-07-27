"""Attach structured phase context to an existing domain exception."""

from streambuild.diagnostics.models import CompilerDiagnostic, SourceLocation
from streambuild.diagnostics.types import DiagnosticPhase, DiagnosticSeverity


def attach_error_diagnostic(
    *,
    error: Exception,
    phase: DiagnosticPhase,
    code: str,
    resource_name: str | None = None,
    location: SourceLocation | None = None,
) -> Exception:
    """Return the same exception with a diagnostic unless its owner already supplied one."""

    existing_diagnostic: object = getattr(error, "diagnostic", None)
    if not isinstance(existing_diagnostic, CompilerDiagnostic):
        owned_location: object = getattr(error, "location", None)
        effective_location: SourceLocation | None = (
            owned_location if isinstance(owned_location, SourceLocation) else location
        )
        error.__dict__["diagnostic"] = CompilerDiagnostic(
            phase=phase,
            severity=DiagnosticSeverity.ERROR,
            code=code,
            message=str(error),
            resource_name=resource_name,
            location=effective_location,
        )
    return error
