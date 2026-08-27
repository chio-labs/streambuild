"""Dev server exceptions."""


class DevServerError(RuntimeError):
    """Raised when the dev server cannot satisfy a request."""


class DevConfigurationError(DevServerError):
    """Raised when retained dev server configuration is internally inconsistent."""


class KafkaCollectorClosedError(DevServerError):
    """Raised when Kafka metadata is requested after its retained clients close."""


class ProjectNotCompiledError(DevServerError):
    """Raised when a request needs definitions but the project compile is failing."""


class BuildInProgressError(DevServerError):
    """Raised when a build is requested while another one is still running."""


class BuildStartError(DevServerError):
    """Raised when a spawned build exits or stalls before its run_started event."""


class AuditSchedulerPersistenceError(DevServerError):
    """Raised when a scheduled slot cannot be durably marked as attempted."""


class MessageQueryValidationError(DevServerError):
    """Raised when a message browsing document names an unsupported field or value."""


class MessageSchemaError(DevServerError):
    """Raised when a raw landing table predates the header-array landing schema."""
