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


class QualityResultStatus(StrEnum):
    """Persisted status of one audit or SQL-test attempt."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    ERROR = "error"
    DEFERRED = "deferred"
