"""Exceptions for compiler-side SQL test assembly."""


class SqlTestAssemblyError(ValueError):
    """Raised when a SQL test cannot be assembled against the compiled graph."""
