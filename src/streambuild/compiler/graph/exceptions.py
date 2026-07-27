"""Dependency graph exceptions."""


class GraphInputError(ValueError):
    """Raised when compiled dependencies do not form a valid project graph."""
