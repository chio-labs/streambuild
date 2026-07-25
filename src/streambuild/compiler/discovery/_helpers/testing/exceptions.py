"""Exceptions for SQL-native test discovery."""


class SqlTestParseError(ValueError):
    """Raised when an authored SQL test file has an invalid shape."""
