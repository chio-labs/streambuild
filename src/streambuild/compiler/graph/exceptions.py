"""Dependency graph exceptions."""

from streambuild.diagnostics.models import CompilerDiagnostic, SourceLocation


class GraphInputError(ValueError):
    """Raised when compiled dependencies do not form a valid project graph."""

    def __init__(self, message: str, *, location: SourceLocation | None = None) -> None:
        super().__init__(message)
        self.location: SourceLocation | None = location
        self.diagnostic: CompilerDiagnostic | None = None
