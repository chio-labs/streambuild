"""Runtime models for SQL audit execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.executor.auditing.types import AuditSeverity


@dataclass(frozen=True)
class SqlAuditResult:
    """One executed SQL audit and its outcome."""

    file_path: Path
    referenced_model_names: tuple[str, ...]
    severity: str
    passed: bool
    failing_row_count: int
    sample_column_names: tuple[str, ...]
    sample_rows: tuple[tuple[object, ...], ...]
    description: str | None = None
    name: str | None = None
    error_message: str | None = None
    deferred_until: str | None = None
    missing_relation_names: tuple[str, ...] = ()

    @property
    def deferred(self) -> bool:
        """Return whether execution was deferred for warmup or materialization."""

        return self.deferred_until is not None or bool(self.missing_relation_names)


@dataclass(frozen=True)
class SqlAuditRunResult:
    """Aggregate outcome for a batch of SQL audits."""

    audit_results: tuple[SqlAuditResult, ...]

    @property
    def error_failure_count(self) -> int:
        return sum(
            1
            for audit_result in self.audit_results
            if audit_result.severity == AuditSeverity.ERROR
            and not audit_result.passed
            and not audit_result.deferred
        )

    @property
    def warning_failure_count(self) -> int:
        return sum(
            1
            for audit_result in self.audit_results
            if audit_result.severity == AuditSeverity.WARNING
            and not audit_result.passed
            and not audit_result.deferred
        )


@dataclass(frozen=True)
class AuditWarmupState:
    """Eligibility of one audit relative to its newest referenced model anchor."""

    eligible: bool
    anchor: str | None
    eligible_at: str | None
    missing_model_names: tuple[str, ...] = ()
