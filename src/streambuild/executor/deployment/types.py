"""Deployment lifecycle types."""

from enum import StrEnum


class DeploymentLifecycleState(StrEnum):
    """Authoritative state derived from metadata and live catalog evidence."""

    ACTIVE = "active"
    STAGED = "staged"
    SUPERSEDED = "superseded"
    INCOMPLETE = "incomplete"
    METADATA_MISSING = "metadata_missing"
    PHYSICAL_MISSING = "physical_missing"
