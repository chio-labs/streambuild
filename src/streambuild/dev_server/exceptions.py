"""Dev server exceptions."""


class DevServerError(RuntimeError):
    """Raised when the dev server cannot satisfy a request."""


class ProjectNotCompiledError(DevServerError):
    """Raised when a request needs definitions but the project compile is failing."""


class BuildInProgressError(DevServerError):
    """Raised when a build is requested while another one is still running."""


class BuildStartError(DevServerError):
    """Raised when a spawned build exits or stalls before its run_started event."""
