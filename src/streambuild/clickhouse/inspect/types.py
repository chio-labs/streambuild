"""ClickHouse inspection runtime domain types."""

from enum import StrEnum


class RootDeploymentStateKind(StrEnum):
    """How one managed root presents itself in the warehouse."""

    ACTIVE_VIEW_PRESENT = "active_view_present"
    GREENFIELD = "greenfield"
    LOGICAL_VIEW_MISSING = "logical_view_missing"
    INVALID_ACTIVE_VIEW = "invalid_active_view"
