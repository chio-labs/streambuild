from __future__ import annotations

import json
from pathlib import Path

from streambuild.cli.commands.main.shared._helpers.styling import (
    format_bool,
    format_count,
    format_percentage,
    format_range,
    humanize_deployment_status,
    style_assessment,
    style_assessment_value,
    style_label,
    style_label_value,
    style_object_name,
    style_section,
    style_title,
    style_warning,
)
from streambuild.executor.audit_backfill.models import AuditBackfillResult
from streambuild.executor.audit_backfill.types import AuditAssessment


def render_audit_backfill_result(
    *,
    result: AuditBackfillResult,
    database: str,
    json_output: bool,
    project_dir: Path | None = None,
) -> str:
    if json_output:
        payload: dict[str, object] = {
            "deployment_id": result.deployment_id,
            "deployment_status": result.deployment_status,
            "assessment": result.assessment,
            "replay_lineage_mode": result.replay_lineage_mode,
            "warning_codes": list(result.warning_codes),
            "root_results": [
                {
                    "name": root_result.root_key.name,
                    "state": root_result.state,
                    "replay_source_name": root_result.replay_source_name,
                    "replay_source_row_count": root_result.replay_source_row_count,
                    "staged_exists": root_result.staged_exists,
                    "active_exists": root_result.active_exists,
                    "active_row_count": root_result.active_row_count,
                    "staged_row_count": root_result.staged_row_count,
                    "row_delta": root_result.row_delta,
                    "row_ratio": root_result.row_ratio,
                    "assessment": root_result.assessment,
                    "replay_lineage_mode": root_result.replay_lineage_mode,
                    "offset_catchup_summary": None
                    if root_result.offset_catchup_summary is None
                    else {
                        "active_partition_count": (
                            root_result.offset_catchup_summary.active_partition_count
                        ),
                        "staged_partition_count": (
                            root_result.offset_catchup_summary.staged_partition_count
                        ),
                        "partitions_compared": (
                            root_result.offset_catchup_summary.partitions_compared
                        ),
                        "missing_staged_partition_count": (
                            root_result.offset_catchup_summary.missing_staged_partition_count
                        ),
                        "missing_freshness_partition_count": (
                            root_result.offset_catchup_summary.missing_freshness_partition_count
                        ),
                        "lagging_partition_count": (
                            root_result.offset_catchup_summary.lagging_partition_count
                        ),
                        "max_offset_gap": root_result.offset_catchup_summary.max_offset_gap,
                        "average_offset_gap": (
                            root_result.offset_catchup_summary.average_offset_gap
                        ),
                        "lag_boundary_column": (
                            root_result.offset_catchup_summary.lag_boundary_column
                        ),
                        "max_lag_seconds": (root_result.offset_catchup_summary.max_lag_seconds),
                        "average_lag_seconds": (
                            root_result.offset_catchup_summary.average_lag_seconds
                        ),
                    },
                    "scalar_catchup_summary": None
                    if root_result.scalar_catchup_summary is None
                    else {
                        "active_min_value": root_result.scalar_catchup_summary.active_min_value,
                        "active_max_value": root_result.scalar_catchup_summary.active_max_value,
                        "staged_min_value": root_result.scalar_catchup_summary.staged_min_value,
                        "staged_max_value": root_result.scalar_catchup_summary.staged_max_value,
                        "lag_seconds": root_result.scalar_catchup_summary.lag_seconds,
                    },
                    "warnings": list(root_result.warnings),
                }
                for root_result in result.root_results
            ],
            "quality_check_results": [
                {
                    "file_path": _display_path(
                        file_path=audit_result.file_path, project_dir=project_dir
                    ),
                    "name": audit_result.name,
                    "severity": audit_result.severity,
                    "passed": audit_result.passed,
                    "referenced_model_names": list(audit_result.referenced_model_names),
                    "description": audit_result.description,
                    "failing_row_count": audit_result.failing_row_count,
                }
                for audit_result in result.quality_check_results
            ],
        }
        return json.dumps(payload, indent=2)

    lines: list[str] = [
        style_title("Audit") + f": {style_assessment(result.assessment)}",
        style_label_value(label="Database", value=database),
        style_label_value(label="Deployment", value=result.deployment_id),
        style_label_value(
            label="Deployment status", value=humanize_deployment_status(result.deployment_status)
        ),
    ]
    if result.replay_lineage_mode is not None:
        lines.append(style_label_value(label="Replay lineage", value=result.replay_lineage_mode))
    if result.warning_codes:
        lines.append(style_warning(f"Warnings: {', '.join(result.warning_codes)}"))
    lines.append("")
    lines.append(style_section("Roots"))
    for root_result in result.root_results:
        assessment: AuditAssessment = AuditAssessment(root_result.assessment)
        lines.append(
            f"- {style_object_name(text=root_result.root_key.name, assessment=assessment)}"
        )
        lines.append(f"  {style_label('state')}: {root_result.state}")
        lines.append(f"  {style_label('assessment')}: {style_assessment(root_result.assessment)}")
        if root_result.replay_source_name is not None:
            lines.append(
                "  "
                f"{style_label('replay source')}: "
                f"{style_object_name(text=root_result.replay_source_name)}"
            )
            lines.append(
                "  "
                f"{style_label('replay source rows')}: "
                f"{format_count(root_result.replay_source_row_count)}"
            )
        lines.append(f"  {style_label('staged exists')}: {format_bool(root_result.staged_exists)}")
        lines.append(f"  {style_label('active exists')}: {format_bool(root_result.active_exists)}")
        lines.append(
            f"  {style_label('staged rows')}: {format_count(root_result.staged_row_count)}"
        )
        lines.append(
            f"  {style_label('active rows')}: {format_count(root_result.active_row_count)}"
        )
        if root_result.row_delta is not None and root_result.row_ratio is not None:
            row_delta_text: str = f"{root_result.row_delta:+d}"
            row_ratio_text: str = format_percentage(root_result.row_ratio)
            if assessment != AuditAssessment.READY:
                row_delta_text = style_assessment_value(text=row_delta_text, assessment=assessment)
                row_ratio_text = style_assessment_value(text=row_ratio_text, assessment=assessment)
            lines.append(f"  {style_label('row delta')}: {row_delta_text}")
            lines.append(f"  {style_label('row ratio')}: {row_ratio_text}")
        if root_result.scalar_catchup_summary is not None:
            staged_range: str = format_range(
                min_value=root_result.scalar_catchup_summary.staged_min_value,
                max_value=root_result.scalar_catchup_summary.staged_max_value,
            )
            active_range: str = format_range(
                min_value=root_result.scalar_catchup_summary.active_min_value,
                max_value=root_result.scalar_catchup_summary.active_max_value,
            )
            lines.append(f"  {style_label('staged range')}: {staged_range}")
            lines.append(f"  {style_label('active range')}: {active_range}")
            if root_result.scalar_catchup_summary.lag_seconds is not None:
                lag_seconds: int = int(root_result.scalar_catchup_summary.lag_seconds)
                lines.append(f"  {style_label('lag seconds')}: {lag_seconds}")
        if root_result.staged_row_count == 0:
            lines.append(f"  {style_label('warning')}: {style_warning('staged table is empty')}")
        warning: str
        for warning in root_result.warnings:
            lines.append(f"  {style_label('warning')}: {style_warning(warning)}")
    if result.quality_check_results:
        lines.append("")
        lines.append(style_section("Quality Checks"))
        for audit_result in result.quality_check_results:
            status: str = "PASS"
            if not audit_result.passed:
                status = "WARN" if audit_result.severity == "warning" else "FAIL"
            display_name: str = _display_path(
                file_path=audit_result.file_path, project_dir=project_dir
            )
            if audit_result.name is not None:
                display_name = f"{display_name}  [{audit_result.name}]"
            lines.append(f"- {status}  {display_name}")
            if audit_result.description is not None:
                lines.append(f"  {style_label('description')}: {audit_result.description}")
            if not audit_result.passed:
                failing_rows_text: str = format_count(audit_result.failing_row_count)
                lines.append(f"  {style_label('failing rows')}: {failing_rows_text}")
    lines.append("")
    lines.append(style_section("Next"))
    if result.assessment == AuditAssessment.READY:
        lines.append(f"- stb publish --deployment-id {result.deployment_id}")
    else:
        affected_root_names: tuple[str, ...] = tuple(
            root_result.root_key.name
            for root_result in result.root_results
            if root_result.assessment != AuditAssessment.READY
        )
        lines.append(
            "- investigate audit findings before publish"
            if not affected_root_names
            else "- investigate audit findings before publish, especially for "
            + ", ".join(affected_root_names)
        )
    return "\n".join(lines)


def _display_path(*, file_path: Path, project_dir: Path | None) -> str:
    if project_dir is None:
        return str(file_path)
    try:
        return str(file_path.relative_to(project_dir))
    except ValueError:
        return str(file_path)
