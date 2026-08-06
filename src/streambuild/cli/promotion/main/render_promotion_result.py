"""Render a deployment promotion result for CLI output."""

from __future__ import annotations

import json

from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.executor.promotion.models import PublishedView, PublishResult


def render_promotion_result(
    *,
    result: PublishResult,
    database: str,
    json_output: bool,
) -> str:
    if json_output:
        payload: dict[str, object] = {
            "deployment_id": result.deployment_id,
            "atomicity": {
                "per_relation_atomic_replace": result.per_relation_atomic_replace,
                "graph_atomic_publish": result.graph_atomic_publish,
            },
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
        cli_style().title("Promotion Complete"),
        cli_style().label_value(label="Database", value=database),
        cli_style().label_value(label="Deployment", value=result.deployment_id),
        "",
        cli_style().section("Published views"),
    ]
    view: PublishedView
    for view in result.published_views:
        lines.append(f"- {view.view_name} -> {view.target_table_name}")
    atomicity_label: dict[bool, str] = {True: "atomic", False: "not atomic"}
    lines.append("")
    lines.append(cli_style().section("Atomicity"))
    lines.append(
        f"- Each logical binding replacement: {atomicity_label[result.per_relation_atomic_replace]}"
    )
    lines.append(f"- Entire deployment promotion: {atomicity_label[result.graph_atomic_publish]}")
    lines.append("- Bindings are replaced one relation at a time")
    lines.append("")
    lines.append(cli_style().section("Next"))
    lines.append("- audit the live logical views in ClickHouse if you want a post-promotion check")
    return "\n".join(lines)
