"""Dev server exceptions."""


class DevServerError(RuntimeError):
    """Raised when the dev server cannot satisfy a request."""


class ProjectNotCompiledError(DevServerError):
    """Raised when a request needs definitions but the project compile is failing."""
