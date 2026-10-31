"""Authentication enums and public type declarations."""

from enum import StrEnum


class AuthenticationMode(StrEnum):
    """Configured server authentication mechanism."""

    DISABLED = "disabled"
    PASSWORD = "password"
    TRUSTED_PROXY = "trusted_proxy"


class AuthenticationSource(StrEnum):
    """Mechanism that authenticated one request."""

    LOCAL = "local"
    PASSWORD = "password"
    TRUSTED_PROXY = "trusted_proxy"


class UnknownUserPolicy(StrEnum):
    """Trusted-proxy behavior for an identity absent from the control store."""

    AUTO_PROVISION = "auto_provision"
    DENY = "deny"
