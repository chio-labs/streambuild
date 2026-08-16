"""Account-administration CLI command types."""

from enum import StrEnum


class AdminCommand(StrEnum):
    """Supported operator account-administration commands."""

    MIGRATE = "migrate"
    CREATE_USER = "create-user"
    GRANT_ROLE = "grant-role"
    REVOKE_ROLE = "revoke-role"
    ENABLE_USER = "enable-user"
    DISABLE_USER = "disable-user"
    RESET_PASSWORD = "reset-password"
