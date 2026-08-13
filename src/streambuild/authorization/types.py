"""Closed authorization decision reasons."""

from enum import StrEnum


class AuthorizationReason(StrEnum):
    """Stable explanation category for one operational decision."""

    SYSTEM_ADMIN = "system_admin"
    GRANTED = "granted"
    POLICY_ABSENT = "policy_absent"
    NO_MATCHING_ASSIGNMENT = "no_matching_assignment"
    STALE_ASSIGNMENT = "stale_assignment"
    EMPTY_PIPELINE_SCOPE = "empty_pipeline_scope"
    MISSING_PERMISSION = "missing_permission"
    MISSING_PIPELINES = "missing_pipelines"
