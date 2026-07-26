from __future__ import annotations

import json
from pathlib import Path

from streambuild.cli.audit_backfill.main._format_bool import format_bool
from streambuild.cli.audit_backfill.main._format_count import format_count
from streambuild.cli.audit_backfill.main._format_percentage import format_percentage
from streambuild.cli.audit_backfill.main._format_range import format_range
from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.cli.presentation.main._humanize_deployment_status import (
    humanize_deployment_status,
)
from streambuild.executor.audit_backfill.models import (
    AuditBackfillResult,
    OffsetCatchupSummary,
    RootAuditResult,
    ScalarCatchupSummary,
)
from streambuild.executor.audit_backfill.types import AuditAssessment
from streambuild.executor.auditing.models import SqlAuditResult
from streambuild.executor.auditing.types import AuditResultStatus, AuditSeverity


def render_audit_backfill_json(*, result: AuditBackfillResult, project_dir: Path | None) -> str:
    payload: dict[str, object] = {
        "deployment_id": result.deployment_id,
        "deployment_status": result.deployment_status,
        "assessment": result.assessment,
        "replay_lineage_mode": result.replay_lineage_mode,
        "warning_codes": list(result.warning_codes),
        "root_results": [_root_result_payload(root_result) for root_result in result.root_results],
        "quality_check_results": [
            _quality_check_payload(audit_result=audit_result, project_dir=project_dir)
            for audit_result in result.quality_check_results
        ],
    }
    return json.dumps(payload, indent=2)


def render_audit_backfill_text(
    *, result: AuditBackfillResult, database: str, project_dir: Path | None
) -> str:
    lines: list[str] = _render_audit_header(result=result, database=database)
    lines.extend(_render_root_results(result.root_results))
    lines.extend(
        _render_quality_check_results(
            audit_results=result.quality_check_results,
            project_dir=project_dir,
        )
    )
    lines.extend(_render_next_steps(result))
    return "\n".join(lines)


def _root_result_payload(root_result: RootAuditResult) -> dict[str, object]:
    return {
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
        "offset_catchup_summary": _offset_catchup_payload(root_result.offset_catchup_summary),
        "scalar_catchup_summary": _scalar_catchup_payload(root_result.scalar_catchup_summary),
        "warnings": list(root_result.warnings),
    }


def _offset_catchup_payload(
    summary: OffsetCatchupSummary | None,
) -> dict[str, object] | None:
    if summary is None:
        return None
    return {
        "active_partition_count": summary.active_partition_count,
        "staged_partition_count": summary.staged_partition_count,
        "partitions_compared": summary.partitions_compared,
        "missing_staged_partition_count": summary.missing_staged_partition_count,
        "missing_freshness_partition_count": summary.missing_freshness_partition_count,
        "lagging_partition_count": summary.lagging_partition_count,
        "max_offset_gap": summary.max_offset_gap,
        "average_offset_gap": summary.average_offset_gap,
        "lag_boundary_column": summary.lag_boundary_column,
        "max_lag_seconds": summary.max_lag_seconds,
        "average_lag_seconds": summary.average_lag_seconds,
    }


def _scalar_catchup_payload(
    summary: ScalarCatchupSummary | None,
) -> dict[str, object] | None:
    if summary is None:
        return None
    return {
        "active_min_value": summary.active_min_value,
        "active_max_value": summary.active_max_value,
        "staged_min_value": summary.staged_min_value,
        "staged_max_value": summary.staged_max_value,
        "lag_seconds": summary.lag_seconds,
    }


def _quality_check_payload(
    *, audit_result: SqlAuditResult, project_dir: Path | None
) -> dict[str, object]:
    return {
        "file_path": _display_path(
            file_path=audit_result.file_path,
            project_dir=project_dir,
        ),
        "name": audit_result.name,
        "severity": audit_result.severity,
        "passed": audit_result.passed,
        "referenced_model_names": list(audit_result.referenced_model_names),
        "description": audit_result.description,
        "failing_row_count": audit_result.failing_row_count,
    }


def _render_audit_header(*, result: AuditBackfillResult, database: str) -> list[str]:
    lines: list[str] = [
        cli_style().title("Audit") + f": {cli_style().assessment(result.assessment)}",
        cli_style().label_value(label="Database", value=database),
        cli_style().label_value(label="Deployment", value=result.deployment_id),
        cli_style().label_value(
            label="Deployment status",
            value=humanize_deployment_status(result.deployment_status),
        ),
    ]
    if result.replay_lineage_mode is not None:
        lines.append(
            cli_style().label_value(label="Replay lineage", value=result.replay_lineage_mode)
        )
    if result.warning_codes:
        lines.append(cli_style().warning(f"Warnings: {', '.join(result.warning_codes)}"))
    lines.append("")
    lines.append(cli_style().section("Roots"))
    return lines


def _render_root_results(root_results: tuple[RootAuditResult, ...]) -> list[str]:
    lines: list[str] = []
    root_result: RootAuditResult
    for root_result in root_results:
        lines.extend(_render_root_result(root_result))
    return lines


def _render_root_result(root_result: RootAuditResult) -> list[str]:
    assessment: AuditAssessment = AuditAssessment(root_result.assessment)
    lines: list[str] = [
        f"- {cli_style().object_name(text=root_result.root_key.name, assessment=assessment)}",
        f"  {cli_style().label('state')}: {root_result.state}",
        (f"  {cli_style().label('assessment')}: {cli_style().assessment(root_result.assessment)}"),
    ]
    if root_result.replay_source_name is not None:
        lines.append(
            "  "
            f"{cli_style().label('replay source')}: "
            f"{cli_style().object_name(text=root_result.replay_source_name)}"
        )
        lines.append(
            "  "
            f"{cli_style().label('replay source rows')}: "
            f"{format_count(root_result.replay_source_row_count)}"
        )
    lines.extend(
        [
            (f"  {cli_style().label('staged exists')}: {format_bool(root_result.staged_exists)}"),
            (f"  {cli_style().label('active exists')}: {format_bool(root_result.active_exists)}"),
            (f"  {cli_style().label('staged rows')}: {format_count(root_result.staged_row_count)}"),
            (f"  {cli_style().label('active rows')}: {format_count(root_result.active_row_count)}"),
        ]
    )
    lines.extend(_render_row_comparison(root_result=root_result, assessment=assessment))
    lines.extend(_render_scalar_catchup(root_result.scalar_catchup_summary))
    if root_result.staged_row_count == 0:
        lines.append(
            f"  {cli_style().label('warning')}: {cli_style().warning('staged table is empty')}"
        )
    warning: str
    for warning in root_result.warnings:
        lines.append(f"  {cli_style().label('warning')}: {cli_style().warning(warning)}")
    return lines


def _render_row_comparison(
    *, root_result: RootAuditResult, assessment: AuditAssessment
) -> list[str]:
    if root_result.row_delta is None or root_result.row_ratio is None:
        return []
    row_delta_text: str = f"{root_result.row_delta:+d}"
    row_ratio_text: str = format_percentage(root_result.row_ratio)
    if assessment != AuditAssessment.READY:
        row_delta_text = cli_style().assessment_value(
            text=row_delta_text,
            assessment=assessment,
        )
        row_ratio_text = cli_style().assessment_value(
            text=row_ratio_text,
            assessment=assessment,
        )
    return [
        f"  {cli_style().label('row delta')}: {row_delta_text}",
        f"  {cli_style().label('row ratio')}: {row_ratio_text}",
    ]


def _render_scalar_catchup(summary: ScalarCatchupSummary | None) -> list[str]:
    if summary is None:
        return []
    staged_range: str = format_range(
        min_value=summary.staged_min_value,
        max_value=summary.staged_max_value,
    )
    active_range: str = format_range(
        min_value=summary.active_min_value,
        max_value=summary.active_max_value,
    )
    lines: list[str] = [
        f"  {cli_style().label('staged range')}: {staged_range}",
        f"  {cli_style().label('active range')}: {active_range}",
    ]
    if summary.lag_seconds is not None:
        lag_seconds: int = int(summary.lag_seconds)
        lines.append(f"  {cli_style().label('lag seconds')}: {lag_seconds}")
    return lines


def _render_quality_check_results(
    *, audit_results: tuple[SqlAuditResult, ...], project_dir: Path | None
) -> list[str]:
    if not audit_results:
        return []
    lines: list[str] = ["", cli_style().section("Quality Checks")]
    audit_result: SqlAuditResult
    for audit_result in audit_results:
        status: AuditResultStatus = _audit_result_status(audit_result)
        display_name: str = _display_path(
            file_path=audit_result.file_path,
            project_dir=project_dir,
        )
        if audit_result.name is not None:
            display_name = f"{display_name}  [{audit_result.name}]"
        lines.append(f"- {status}  {display_name}")
        if audit_result.description is not None:
            lines.append(f"  {cli_style().label('description')}: {audit_result.description}")
        if not audit_result.passed:
            failing_rows_text: str = format_count(audit_result.failing_row_count)
            lines.append(f"  {cli_style().label('failing rows')}: {failing_rows_text}")
    return lines


def _render_next_steps(result: AuditBackfillResult) -> list[str]:
    lines: list[str] = ["", cli_style().section("Next")]
    if result.assessment == AuditAssessment.READY:
        lines.append(f"- stb publish --deployment-id {result.deployment_id}")
        return lines
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
    return lines


def _audit_result_status(audit_result: SqlAuditResult) -> AuditResultStatus:
    if audit_result.passed:
        return AuditResultStatus.PASS
    if audit_result.severity == AuditSeverity.WARNING:
        return AuditResultStatus.WARN
    return AuditResultStatus.FAIL


def _display_path(*, file_path: Path, project_dir: Path | None) -> str:
    if project_dir is None:
        return str(file_path)
    try:
        return str(file_path.relative_to(project_dir))
    except ValueError:
        return str(file_path)
