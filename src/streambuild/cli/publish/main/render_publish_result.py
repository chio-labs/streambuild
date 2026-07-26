"""Render the publish result for CLI output."""

from __future__ import annotations

import json

from streambuild.cli.shared.main._cli_style import cli_style
from streambuild.executor.publish.models import PublishedView, PublishResult


def render_publish_result(
    *,
    result: PublishResult,
    database: str,
    json_output: bool,
) -> str:
    if json_output:
        payload: dict[str, object] = {
            "deployment_id": result.deployment_id,
            "published_views": [
                {
                    "view_name": view.view_name,
                    "target_table_name": view.target_table_name,
                }
                for view in result.published_views
            ],
        }
        return json.dumps(payload, indent=2)

    lines: list[str] = [
        cli_style().title("Publish Complete"),
        cli_style().label_value(label="Database", value=database),
        cli_style().label_value(label="Deployment", value=result.deployment_id),
        "",
        cli_style().section("Published views"),
    ]
    view: PublishedView
    for view in result.published_views:
        lines.append(f"- {view.view_name} -> {view.target_table_name}")
    lines.append("")
    lines.append(cli_style().section("Next"))
    lines.append("- audit the live logical views in ClickHouse if you want a post-publish check")
    return "\n".join(lines)
