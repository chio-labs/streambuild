"""Apache-2.0: SQLBuild provider/exceptions.py@7625d22e2716."""


class ProviderInputError(ValueError):
    """Raised when a provider definition is invalid."""


class ProviderLookupError(LookupError):
    """Raised when a provider cannot be found at runtime."""


class ProviderSetupError(RuntimeError):
    """Raised when provider setup fails."""


class ProviderTeardownError(RuntimeError):
    """Raised when provider teardown fails."""


class ProviderInjectionError(RuntimeError):
    """Raised when a provider cannot be injected into a Python sensor call."""


class ProviderDiscoveryError(ValueError):
    """Raised when project provider discovery fails."""
