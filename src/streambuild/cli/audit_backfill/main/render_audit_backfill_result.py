"""Render the audit backfill result for CLI output."""

from __future__ import annotations

from pathlib import Path

from streambuild.cli.audit_backfill._helpers.rendering import (
    render_audit_backfill_json,
    render_audit_backfill_text,
)
from streambuild.executor.audit_backfill.models import AuditBackfillResult


def render_audit_backfill_result(
    *,
    result: AuditBackfillResult,
    database: str,
    json_output: bool,
    project_dir: Path | None = None,
) -> str:
    if json_output:
        return render_audit_backfill_json(result=result, project_dir=project_dir)
    return render_audit_backfill_text(
        result=result,
        database=database,
        project_dir=project_dir,
    )
