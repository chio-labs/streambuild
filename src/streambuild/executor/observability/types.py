"""Closed observability value domains."""

from enum import StrEnum


class QualityResultTrigger(StrEnum):
    """The execution path that produced one quality result."""

    BUILD = "build"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    DEPLOYMENT = "deployment"


class MaterializationOutcome(StrEnum):
    """Whether a direct mutation workflow safely completed."""

    APPLIED = "applied"
    FAILED = "failed"
