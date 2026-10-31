"""Exceptions for SQL audit discovery."""


class SqlAuditParseError(ValueError):
    """Raised when an authored SQL audit file has an invalid shape."""
