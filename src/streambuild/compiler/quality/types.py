"""Compiled quality node value domains."""

from enum import StrEnum


class QualityNodeKind(StrEnum):
    """Kinds of quality definitions persisted by StreamBuild."""

    AUDIT = "audit"
    TEST = "test"
