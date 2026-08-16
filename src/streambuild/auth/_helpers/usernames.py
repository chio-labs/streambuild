"""Canonical StreamBuild username validation."""

import re

from streambuild.auth.exceptions import AccountValidationError

_USERNAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9][a-z0-9._@+-]{0,127}$")


def canonical_username(value: str) -> str:
    """Validate and canonicalize one StreamBuild username."""

    canonical: str = value.strip().casefold()
    if not _USERNAME_PATTERN.fullmatch(canonical):
        raise AccountValidationError(
            "Username must start with an alphanumeric character and contain only "
            "letters, numbers, '.', '_', '@', '+', or '-'"
        )
    return canonical
