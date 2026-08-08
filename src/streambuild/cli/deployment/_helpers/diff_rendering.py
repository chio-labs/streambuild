"""Render deployment schema and row-count differences."""

import json

from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.executor.deployment.models import (
    DeploymentDiffColumn,
    DeploymentDiffRelation,
    DeploymentDiffResult,
)


def render_deployment_diff(*, result: DeploymentDiffResult, json_output: bool) -> str:
    """Render one deployment comparison as text or JSON."""

    if json_output:
        return json.dumps(
            {
                "database": result.database,
                "from": result.from_endpoint,
                "to": result.to_endpoint,
                "relations": [_relation_payload(relation) for relation in result.relations],
            },
            indent=2,
        )
    lines: list[str] = [
        cli_style().title("Deployment Diff"),
        cli_style().label_value(label="Database", value=result.database),
        cli_style().label_value(
            label="Comparison", value=f"{result.from_endpoint}:{result.to_endpoint}"
        ),
        "",
        cli_style().section("Relations"),
    ]
    if not result.relations:
        lines.append("- none")
        return "\n".join(lines)
    for relation in result.relations:
        lines.append(f"- {relation.database}.{relation.logical_name}: {relation.status}")
        lines.append(
            f"  rows: {_count(relation.from_row_count)} -> {_count(relation.to_row_count)}"
        )
        if relation.from_columns != relation.to_columns:
            lines.append(
                f"  columns: {_columns(relation.from_columns)} -> {_columns(relation.to_columns)}"
            )
    return "\n".join(lines)


def _relation_payload(relation: DeploymentDiffRelation) -> dict[str, object]:
    return {
        "database": relation.database,
        "logical_name": relation.logical_name,
        "status": str(relation.status),
        "from_physical_name": relation.from_physical_name,
        "to_physical_name": relation.to_physical_name,
        "from_columns": [column.__dict__ for column in relation.from_columns],
        "to_columns": [column.__dict__ for column in relation.to_columns],
        "from_row_count": relation.from_row_count,
        "to_row_count": relation.to_row_count,
    }


def _count(value: int | None) -> str:
    return "missing" if value is None else str(value)


def _columns(columns: tuple[DeploymentDiffColumn, ...]) -> str:
    if not columns:
        return "missing"
    return ", ".join(f"{column.name} {column.type}" for column in columns)
