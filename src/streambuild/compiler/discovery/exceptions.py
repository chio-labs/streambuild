"""Discovery exceptions."""

from streambuild.diagnostics.models import CompilerDiagnostic


class PipelineDiscoveryError(ValueError):
    """Raised when discovery input or state is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.diagnostic: CompilerDiagnostic | None = None


class ModelHeaderSyntaxError(ValueError):
    """Raised when a MODEL header does not follow SQLBuild syntax."""


class ProjectSpecError(ValueError):
    """Raised when authored specification input or state is invalid."""


class ProjectConfigError(ProjectSpecError):
    """Raised when project or local configuration is invalid."""


class DurationParseError(ProjectSpecError):
    """Raised when a compact authored duration is invalid."""


class RetentionConfigError(ProjectSpecError):
    """Raised when a typed retention policy is invalid."""
