"""Discovery exceptions."""


class PipelineDiscoveryError(ValueError):
    """Raised when discovery input or state is invalid."""


class ProjectSpecError(ValueError):
    """Raised when authored specification input or state is invalid."""
