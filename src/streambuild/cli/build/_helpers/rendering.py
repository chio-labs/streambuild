"""Render what one direct build durably changed as operator text or JSON."""

from __future__ import annotations

import json

from streambuild.cli.plan.constants import DIRECT_MODE_LABEL
from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.executor.auditing.models import SqlAuditResult, SqlAuditRunResult
from streambuild.executor.direct.models import (
    DirectBuildResult,
    DirectReplayBoundary,
    DirectRootReplayResult,
)

_AUDIT_STATUS_BY_OUTCOME: dict[bool, str] = {True: "pass", False: "FAIL"}


def render_direct_build_json(
    *,
    result: DirectBuildResult,
    adapter_name: str,
    audit_result: SqlAuditRunResult,
) -> str:
    """Render one completed direct build as deterministic JSON."""

    payload: dict[str, object] = {
        "mode": DIRECT_MODE_LABEL,
        "adapter": adapter_name,
        "database": result.database,
        "start_time": result.effective_start_time,
        "preserved_sources": list(result.preserved_source_relation_names),
        "created_sources": list(result.created_source_relation_names),
        "ownership": [record.relation_name for record in result.ownership_records],
        "dropped": list(result.dropped_relation_names),
        "created": list(result.created_relation_names),
        "boundary_time": result.boundary_time,
        "boundaries": [_boundary_payload(boundary) for boundary in result.boundaries],
        "replays": [_replay_payload(replay) for replay in result.replay_results],
        "audits": _audit_payload(audit_result),
    }
    return json.dumps(payload, indent=2)


def render_direct_build_text(
    *,
    result: DirectBuildResult,
    adapter_name: str,
    audit_result: SqlAuditRunResult,
) -> str:
    """Render one completed direct build as operator-facing text."""

    return "\n".join(
        (
            *_render_header(result=result, adapter_name=adapter_name),
            *_render_relations(result=result),
            *_render_boundaries(result=result),
            *_render_replays(result=result),
            *_render_audits(audit_result=audit_result),
        )
    )


def _render_header(*, result: DirectBuildResult, adapter_name: str) -> tuple[str, ...]:
    return (
        cli_style().title("Direct Build Complete"),
        cli_style().label_value(label="Adapter", value=adapter_name),
        cli_style().label_value(label="Mode", value=DIRECT_MODE_LABEL),
        cli_style().label_value(label="Database", value=result.database),
        *(
            (
                cli_style().label_value(
                    label="Effective start time", value=result.effective_start_time
                ),
            )
            if result.effective_start_time is not None
            else ()
        ),
        cli_style().label_value(
            label="Preserved sources", value=str(len(result.preserved_source_relation_names))
        ),
        cli_style().label_value(
            label="Replay roots executed", value=str(len(result.replay_results))
        ),
        "",
    )


def _render_relations(*, result: DirectBuildResult) -> tuple[str, ...]:
    return (
        cli_style().section("Relations"),
        *_or_none(lines=tuple(f"  dropped  {name}" for name in result.dropped_relation_names)),
        *tuple(f"  created  {name}" for name in result.created_relation_names),
        "",
    )


def _render_boundaries(*, result: DirectBuildResult) -> tuple[str, ...]:
    return (
        cli_style().section("Replay boundaries"),
        cli_style().label_value(label="Boundary time", value=result.boundary_time),
        *_or_none(
            lines=tuple(_render_boundary(boundary) for boundary in result.boundaries),
        ),
        "",
    )


def _render_boundary(boundary: DirectReplayBoundary) -> str:
    edge: str = "<=" if boundary.cutoff_inclusive else "<"
    return (
        f"  {boundary.model_name} replays {boundary.driving_input_relation_name} "
        f"where {boundary.boundary_key} {edge} {boundary.cutoff_value}"
    )


def _render_replays(*, result: DirectBuildResult) -> tuple[str, ...]:
    return (
        cli_style().section("Replay execution"),
        *_or_none(lines=tuple(_render_replay(replay) for replay in result.replay_results)),
        "",
    )


def _render_replay(replay: DirectRootReplayResult) -> str:
    written_rows: str = "unavailable" if replay.written_rows is None else str(replay.written_rows)
    return f"  {replay.model_name}  warehouse-written rows: {written_rows}"


def _render_audits(*, audit_result: SqlAuditRunResult) -> tuple[str, ...]:
    return (
        cli_style().section("Audits"),
        *_or_none(lines=tuple(_render_audit(audit) for audit in audit_result.audit_results)),
    )


def _render_audit(audit: SqlAuditResult) -> str:
    status: str = _AUDIT_STATUS_BY_OUTCOME[audit.passed]
    return f"  {status}  {_audit_label(audit)}  ({audit.failing_row_count} failing rows)"


def _audit_label(audit: SqlAuditResult) -> str:
    return audit.name or audit.file_path.name


def _boundary_payload(boundary: DirectReplayBoundary) -> dict[str, object]:
    return {
        "model": boundary.model_name,
        "driving_input_relation": boundary.driving_input_relation_name,
        "replay_boundary_mode": str(boundary.replay_boundary_mode),
        "boundary_key": boundary.boundary_key,
        "cutoff_value": boundary.cutoff_value,
        "cutoff_inclusive": boundary.cutoff_inclusive,
    }


def _replay_payload(replay: DirectRootReplayResult) -> dict[str, object]:
    return {
        "model": replay.model_name,
        "warehouse_written_rows": replay.written_rows,
    }


def _audit_payload(audit_result: SqlAuditRunResult) -> list[dict[str, object]]:
    return [
        {
            "name": _audit_label(audit),
            "passed": audit.passed,
            "failing_row_count": audit.failing_row_count,
            "severity": str(audit.severity),
        }
        for audit in audit_result.audit_results
    ]


def _or_none(*, lines: tuple[str, ...]) -> tuple[str, ...]:
    return lines or ("  - none",)
