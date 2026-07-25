"""Rendering helpers for live SQL audit results."""

from __future__ import annotations

import json
from pathlib import Path

from streambuild.cli.commands.main.shared._helpers.styling import (
    style_label_value,
    style_section,
    style_title,
)
from streambuild.executor.auditing.models import SqlAuditResult, SqlAuditRunResult


def render_sql_audit_run_result(
    result: SqlAuditRunResult,
    *,
    database: str,
    project_dir: Path,
    json_output: bool,
) -> str:
    """Render a live SQL audit run result."""

    if json_output:
        return json.dumps(
            {
                "database": database,
                "error_failure_count": result.error_failure_count,
                "warning_failure_count": result.warning_failure_count,
                "audit_results": [
                    {
                        "file_path": _display_path(audit_result.file_path, project_dir),
                        "name": audit_result.name,
                        "severity": audit_result.severity,
                        "passed": audit_result.passed,
                        "referenced_model_names": list(audit_result.referenced_model_names),
                        "description": audit_result.description,
                        "failing_row_count": audit_result.failing_row_count,
                        "sample_column_names": list(audit_result.sample_column_names),
                        "sample_rows": [list(row) for row in audit_result.sample_rows],
                    }
                    for audit_result in result.audit_results
                ],
            },
            indent=2,
        )

    lines: list[str] = [
        style_title("Audit Results"),
        style_label_value("Database", database),
        "",
    ]
    lines.extend(
        _render_group(
            title="Errors",
            audit_results=tuple(
                audit_result
                for audit_result in result.audit_results
                if audit_result.severity == "error" and not audit_result.passed
            ),
            project_dir=project_dir,
        )
    )
    lines.append("")
    lines.extend(
        _render_group(
            title="Warnings",
            audit_results=tuple(
                audit_result
                for audit_result in result.audit_results
                if audit_result.severity == "warning" and not audit_result.passed
            ),
            project_dir=project_dir,
        )
    )
    lines.append("")
    lines.append(
        f"Result: {'FAIL' if result.error_failure_count else 'PASS'} "
        f"({result.error_failure_count} errors, {result.warning_failure_count} warnings)"
    )
    return "\n".join(lines)


def _render_group(
    *, title: str, audit_results: tuple[SqlAuditResult, ...], project_dir: Path
) -> list[str]:
    lines: list[str] = [style_section(title)]
    if not audit_results:
        lines.append("(none)")
        return lines
    audit_result: SqlAuditResult
    for audit_result in audit_results:
        lines.append(_render_audit_heading(audit_result, project_dir))
        lines.append(f"    models: {', '.join(audit_result.referenced_model_names)}")
        if audit_result.description is not None:
            lines.append(f"    description: {audit_result.description}")
        lines.append(f"    failing rows: {audit_result.failing_row_count}")
        if audit_result.sample_rows:
            lines.append("    sample:")
            lines.extend(_render_sample_rows(audit_result))
    return lines


def _render_sample_rows(audit_result: SqlAuditResult) -> list[str]:
    header: str = "      | " + " | ".join(audit_result.sample_column_names) + " |"
    lines: list[str] = [header]
    row: tuple[object, ...]
    for row in audit_result.sample_rows:
        lines.append("      | " + " | ".join(str(value) for value in row) + " |")
    return lines


def _display_path(file_path: Path, project_dir: Path) -> str:
    try:
        return str(file_path.relative_to(project_dir))
    except ValueError:
        return str(file_path)


def _render_audit_heading(audit_result: SqlAuditResult, project_dir: Path) -> str:
    display_path: str = _display_path(audit_result.file_path, project_dir)
    if audit_result.name is None:
        return f"- {display_path}"
    return f"- {display_path}  [{audit_result.name}]"
