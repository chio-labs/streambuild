"""Live audit runtime domain types."""

from enum import StrEnum


class AuditSeverity(StrEnum):
    """How a failing audit should be reported."""

    ERROR = "error"
    WARNING = "warning"


class AuditResultStatus(StrEnum):
    """Operator-facing status label for one audit result."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
