"""Planner exceptions."""


class DeploymentPlanError(ValueError):
    """Raised when planner input or state is invalid."""


class ActualStateError(ValueError):
    """Raised when actual-state input or state is invalid."""


class StandardPlanError(ValueError):
    """Raised when a standard-mode plan cannot be built safely."""


class TargetOwnershipConflictError(ValueError):
    """Raised when one mode would take over relations another mode already owns."""
