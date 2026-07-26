"""Planner exceptions."""


class DeploymentPlanError(ValueError):
    """Raised when planner input or state is invalid."""


class ActualStateError(ValueError):
    """Raised when actual-state input or state is invalid."""
