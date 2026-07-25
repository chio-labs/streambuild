from __future__ import annotations

import json

from streambuild.cli.commands.main.shared._helpers.styling import (
    style_label,
    style_label_value,
    style_object_name,
    style_section,
    style_title,
)
from streambuild.executor.backfill.models import BackfillExecutionResult, RootBackfillReport


def render_backfill_result(
    result: BackfillExecutionResult,
    *,
    database: str,
    json_output: bool,
) -> str:
    if json_output:
        payload: dict[str, object] = {
            "deployment_id": result.bootstrap.deployment_id,
            "boundary_time": result.boundary_time,
            "root_reports": [
                {
                    "name": report.root_key.name,
                    "state_kind": report.state_kind,
                    "replay_strategy": report.replay_strategy,
                    "active_deployment_id": report.active_deployment_id,
                }
                for report in result.bootstrap.root_reports
            ],
        }
        return json.dumps(payload, indent=2)

    lines: list[str] = [
        style_title("Backfill Started"),
        style_label_value("Database", database),
        style_label_value("Deployment", result.bootstrap.deployment_id),
        style_label_value("Boundary time", result.boundary_time),
        "",
        style_section("Roots"),
    ]
    report: RootBackfillReport
    for report in result.bootstrap.root_reports:
        lines.append(f"- {style_object_name(report.root_key.name)}")
        lines.append(f"  {style_label('state')}: {report.state_kind}")
        lines.append(f"  {style_label('strategy')}: {report.replay_strategy}")
        if report.active_deployment_id is not None:
            lines.append(f"  {style_label('active deployment')}: {report.active_deployment_id}")
    lines.extend(
        [
            "",
            style_section("Next"),
            f"- stb audit backfill --deployment-id {result.bootstrap.deployment_id}",
            f"- stb publish --deployment-id {result.bootstrap.deployment_id}",
        ]
    )
    return "\n".join(lines)
