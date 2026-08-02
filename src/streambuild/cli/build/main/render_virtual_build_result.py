"""Render a virtual-environment build result for CLI output."""

from __future__ import annotations

import json

from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.executor.backfill.models import (
    BackfillExecutionResult,
    BackfillRootReplayResult,
    RootBackfillReport,
)


def render_virtual_build_result(
    *,
    result: BackfillExecutionResult,
    database: str,
    json_output: bool,
) -> str:
    if json_output:
        payload: dict[str, object] = {
            "deployment_id": result.bootstrap.deployment_id,
            "boundary_time": result.boundary_time,
            "replays": [
                {
                    "root": replay.root_key.name,
                    "warehouse_written_rows": replay.written_rows,
                }
                for replay in result.replay_results
            ],
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
        cli_style().title("Virtual Build Ready"),
        cli_style().label_value(label="Database", value=database),
        cli_style().label_value(label="Deployment", value=result.bootstrap.deployment_id),
        cli_style().label_value(label="Boundary time", value=result.boundary_time),
        "",
        cli_style().section("Roots"),
    ]
    report: RootBackfillReport
    for report in result.bootstrap.root_reports:
        lines.append(f"- {cli_style().object_name(text=report.root_key.name)}")
        lines.append(f"  {cli_style().label('state')}: {report.state_kind}")
        lines.append(f"  {cli_style().label('strategy')}: {report.replay_strategy}")
        if report.active_deployment_id is not None:
            lines.append(
                f"  {cli_style().label('active deployment')}: {report.active_deployment_id}"
            )
    lines.extend(("", cli_style().section("Replay execution")))
    replay: BackfillRootReplayResult
    for replay in result.replay_results:
        written_rows: str = (
            "unavailable" if replay.written_rows is None else str(replay.written_rows)
        )
        lines.append(
            f"- {cli_style().object_name(text=replay.root_key.name)}  "
            f"warehouse-written rows: {written_rows}"
        )
    if not result.replay_results:
        lines.append("- none")
    lines.extend(
        [
            "",
            cli_style().section("Next"),
            f"- stb audit deployment --deployment-id {result.bootstrap.deployment_id}",
            f"- stb publish --deployment-id {result.bootstrap.deployment_id}",
        ]
    )
    return "\n".join(lines)
