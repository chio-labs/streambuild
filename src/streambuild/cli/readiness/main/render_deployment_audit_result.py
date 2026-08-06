"""Render the audit backfill result for CLI output."""

from __future__ import annotations

from pathlib import Path

from streambuild.cli.readiness._helpers.rendering import (
    render_deployment_audit_json,
    render_deployment_audit_text,
)
from streambuild.executor.readiness.models import DeploymentAuditResult


def render_deployment_audit_result(
    *,
    result: DeploymentAuditResult,
    database: str,
    json_output: bool,
    project_dir: Path | None = None,
) -> str:
    if json_output:
        return render_deployment_audit_json(result=result, project_dir=project_dir)
    return render_deployment_audit_text(
        result=result,
        database=database,
        project_dir=project_dir,
    )
