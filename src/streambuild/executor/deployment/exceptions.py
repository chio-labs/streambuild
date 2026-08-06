"""Deployment lifecycle exceptions."""


class DeploymentNotFoundError(ValueError):
    """Raised when an explicit deployment identifier is not present."""
