"""Direct-build execution failures."""


class DirectBuildError(RuntimeError):
    """Raised when a direct build cannot proceed safely."""
