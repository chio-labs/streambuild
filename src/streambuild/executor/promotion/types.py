"""Promotion lifecycle domain types."""

from enum import StrEnum


class PublishOperation(StrEnum):
    """Reason stable bindings were published."""

    PROMOTE = "promote"
    ROLLBACK = "rollback"
