"""Render the message shown when a deployment choice is ambiguous."""

from __future__ import annotations

from streambuild.cli.shared.main._cli_style import cli_style
from streambuild.cli.shared.main._humanize_deployment_status import humanize_deployment_status
from streambuild.cli.shared.main._humanize_timestamp import humanize_timestamp
from streambuild.executor.audit_backfill.models import AuditDeploymentCandidate


def render_ambiguous_deployment_message(
    *,
    command_name: str,
    database: str,
    root_names: tuple[str, ...],
    candidates: tuple[AuditDeploymentCandidate, ...],
) -> str:
    sorted_candidates: tuple[AuditDeploymentCandidate, ...] = tuple(
        sorted(candidates, key=lambda candidate: candidate.deployment_id, reverse=True)
    )
    lines: list[str] = [
        cli_style().title(f"{command_name.title()} deployment selection is ambiguous"),
        cli_style().label_value(label="Database", value=database),
        "",
    ]
    if root_names:
        lines.append(cli_style().section("Affected roots"))
        root_name: str
        for root_name in root_names:
            lines.append(f"- {root_name}")
        lines.append("")
    lines.append(cli_style().section("Candidate deployments"))
    candidate: AuditDeploymentCandidate
    for candidate in sorted_candidates:
        lines.append(f"- {candidate.deployment_id}")
        if candidate.created_at is not None:
            lines.append(f"  created at: {humanize_timestamp(candidate.created_at)}")
        if candidate.deployment_status is not None:
            lines.append(f"  status: {humanize_deployment_status(candidate.deployment_status)}")
        if candidate.root_names:
            lines.append(f"  roots: {', '.join(candidate.root_names)}")
    lines.append("")
    lines.append(cli_style().section("Recommended"))
    candidate = sorted_candidates[0]
    lines.append(f"- stb {command_name} --deployment-id {candidate.deployment_id}")
    return "\n".join(lines)
