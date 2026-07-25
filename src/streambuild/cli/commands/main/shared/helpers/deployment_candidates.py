from __future__ import annotations

from streambuild.cli.commands.main.shared.helpers.styling import (
    humanize_deployment_status,
    humanize_timestamp,
    style_label_value,
    style_section,
    style_title,
)
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
        style_title(f"{command_name.title()} deployment selection is ambiguous"),
        style_label_value("Database", database),
        "",
    ]
    if root_names:
        lines.append(style_section("Affected roots"))
        root_name: str
        for root_name in root_names:
            lines.append(f"- {root_name}")
        lines.append("")
    lines.append(style_section("Candidate deployments"))
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
    lines.append(style_section("Recommended"))
    candidate = sorted_candidates[0]
    lines.append(f"- stb {command_name} --deployment-id {candidate.deployment_id}")
    return "\n".join(lines)


def render_no_deployment_candidates_message(*, command_name: str, database: str) -> str:
    return "\n".join(
        [
            style_title(f"No staged deployment candidates are available for {command_name}"),
            style_label_value("Database", database),
        ]
    )
