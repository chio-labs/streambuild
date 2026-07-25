"""Runtime models for SQL audit execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class SqlAuditRunResult:
    """Aggregate outcome for a batch of SQL audits."""

    audit_results: tuple[SqlAuditResult, ...]

    @property
    def error_failure_count(self) -> int:
        return sum(
            1
            for audit_result in self.audit_results
            if audit_result.severity == "error" and not audit_result.passed
        )

    @property
    def warning_failure_count(self) -> int:
        return sum(
            1
            for audit_result in self.audit_results
            if audit_result.severity == "warning" and not audit_result.passed
        )
