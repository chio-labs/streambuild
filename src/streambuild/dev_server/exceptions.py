"""Dev server exceptions."""


class DevServerError(RuntimeError):
    """Raised when the dev server cannot satisfy a request."""


class DevConfigurationError(DevServerError):
    """Raised when retained dev server configuration is internally inconsistent."""


class ProjectNotCompiledError(DevServerError):
    """Raised when a request needs definitions but the project compile is failing."""


class BuildInProgressError(DevServerError):
    """Raised when a build is requested while another one is still running."""


class BuildStartError(DevServerError):
    """Raised when a spawned build exits or stalls before its run_started event."""


class AuditSchedulerPersistenceError(DevServerError):
    """Raised when a scheduled slot cannot be durably marked as attempted."""
