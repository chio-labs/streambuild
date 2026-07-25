from __future__ import annotations

import json

from streambuild.cli.commands.main.shared.helpers.styling import (
    style_label_value,
    style_section,
    style_title,
)
from streambuild.executor.publish.models import PublishedView, PublishResult


def render_publish_result(
    result: PublishResult,
    *,
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
        style_title("Publish Complete"),
        style_label_value("Database", database),
        style_label_value("Deployment", result.deployment_id),
        "",
        style_section("Published views"),
    ]
    view: PublishedView
    for view in result.published_views:
        lines.append(f"- {view.view_name} -> {view.target_table_name}")
    lines.append("")
    lines.append(style_section("Next"))
    lines.append("- audit the live logical views in ClickHouse if you want a post-publish check")
    return "\n".join(lines)
