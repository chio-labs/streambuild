"""Deployment lifecycle exceptions."""


class DeploymentNotFoundError(ValueError):
    """Raised when an explicit deployment identifier is not present."""


class DeploymentDiffError(ValueError):
    """Raised when a deployment comparison cannot be resolved safely."""
