"""Render and confirm whole-deployment rollback operations."""

import json

from streambuild.cli.entry.constants import AFFIRMATIVE_RESPONSES
from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.executor.promotion.models import PublishResult, RollbackPlan


def render_rollback_plan(*, plan: RollbackPlan, database: str) -> str:
    """Render the binding-level rollback confirmation summary."""

    lines: list[str] = [
        cli_style().title("Rollback Preview"),
        cli_style().label_value(label="Database", value=database),
        cli_style().label_value(label="Current deployment", value=plan.current_deployment_id),
        cli_style().label_value(label="Target deployment", value=plan.target_deployment_id),
        "",
        cli_style().section("Stable bindings"),
    ]
    lines.extend(f"- {view_name}" for view_name in plan.logical_view_names)
    return "\n".join(lines)


def confirm_rollback() -> bool:
    """Require an affirmative operator response before switching bindings."""

    return input("Proceed with rollback? [y/N] ").strip().lower() in AFFIRMATIVE_RESPONSES


def render_rollback_result(*, result: PublishResult, database: str, json_output: bool) -> str:
    """Render one completed rollback."""

    if json_output:
        return json.dumps(
            {
                "operation": result.operation,
                "database": database,
                "previous_deployment_id": result.previous_deployment_id,
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
            },
            indent=2,
        )
    lines: list[str] = [
        cli_style().title("Rollback Complete"),
        cli_style().label_value(label="Database", value=database),
        cli_style().label_value(
            label="Previous deployment", value=result.previous_deployment_id or "unknown"
        ),
        cli_style().label_value(label="Active deployment", value=result.deployment_id),
        "",
        cli_style().section("Published views"),
    ]
    lines.extend(
        f"- {view.view_name} -> {view.target_table_name}" for view in result.published_views
    )
    lines.extend(
        (
            "",
            cli_style().section("Atomicity"),
            "- Bindings were replaced one relation at a time",
            f"- Entire rollback graph atomic: {result.graph_atomic_publish}",
        )
    )
    return "\n".join(lines)
