"""Authentication and account-domain failures."""


class AuthenticationError(Exception):
    """A request could not produce an authenticated principal."""


class AuthorizationError(Exception):
    """An authenticated principal cannot perform an account operation."""


class ControlStoreError(Exception):
    """The account control store is unavailable or incompatible."""


class AuthConfigurationError(ValueError):
    """Authentication runtime configuration is invalid."""


class AccountValidationError(ValueError):
    """Account input violates a stable domain constraint."""


class PasswordValidationError(ValueError):
    """A password does not meet the configured security policy."""


class AccountConflictError(ControlStoreError):
    """An account mutation conflicts with existing identity state."""


class AccountNotFoundError(ControlStoreError):
    """An account or role assignment does not exist."""
