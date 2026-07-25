from __future__ import annotations

import json
from typing import cast

from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewCandidate,
    JanitorPreviewResult,
)


def render_janitor_result(
    result: JanitorPreviewResult | JanitorApplyResult,
    *,
    apply: bool,
    json_output: bool,
) -> str:
    if apply:
        apply_result: JanitorApplyResult = cast(JanitorApplyResult, result)
    else:
        preview_result: JanitorPreviewResult = cast(JanitorPreviewResult, result)

    if json_output:
        payload: dict[str, object]
        if apply:
            payload = {
                "database": apply_result.database,
                "retention_days": apply_result.retention_days,
                "deleted_deployment_ids": apply_result.deleted_deployment_ids,
                "deleted_object_names": apply_result.deleted_object_names,
            }
        else:
            payload = {
                "database": preview_result.database,
                "retention_days": preview_result.retention_days,
                "candidates": [candidate.__dict__ for candidate in preview_result.candidates],
            }
        return json.dumps(payload, indent=2)

    if apply:
        lines: list[str] = [
            f"Janitor Apply\nDatabase: {apply_result.database}\n"
            f"Retention days: {apply_result.retention_days}\n"
        ]
        if not apply_result.deleted_deployment_ids:
            lines.append("Deleted deployments:\n- none")
            return "\n".join(lines)
        lines.append("Deleted deployments:")
        deployment_id: str
        for deployment_id in apply_result.deleted_deployment_ids:
            lines.append(f"- {deployment_id}")
        lines.append("\nDeleted physical objects:")
        object_name: str
        for object_name in apply_result.deleted_object_names:
            lines.append(f"- {object_name}")
        return "\n".join(lines)

    lines = [
        f"Janitor Preview\nDatabase: {preview_result.database}\n"
        f"Retention days: {preview_result.retention_days}\n"
    ]
    lines.append("Deletable deployments:")
    deletable_candidate: JanitorPreviewCandidate
    deletable_candidates: tuple[JanitorPreviewCandidate, ...] = tuple(
        candidate for candidate in preview_result.candidates if candidate.deletable
    )
    if not deletable_candidates:
        lines.append("- none")
    for deletable_candidate in deletable_candidates:
        lines.append(f"- {deletable_candidate.deployment_id}")
        lines.append(f"  created at: {deletable_candidate.created_at}")
        if deletable_candidate.logical_view_names:
            lines.append(f"  roots: {', '.join(deletable_candidate.logical_view_names)}")
        lines.append(f"  reason: {deletable_candidate.reason}")
        if deletable_candidate.physical_object_names:
            lines.append(
                f"  physical objects: {', '.join(deletable_candidate.physical_object_names)}"
            )
    lines.append("\nKept deployments:")
    kept_candidate: JanitorPreviewCandidate
    kept_candidates: tuple[JanitorPreviewCandidate, ...] = tuple(
        candidate for candidate in preview_result.candidates if not candidate.deletable
    )
    if not kept_candidates:
        lines.append("- none")
    for kept_candidate in kept_candidates:
        lines.append(f"- {kept_candidate.deployment_id}")
        lines.append(f"  created at: {kept_candidate.created_at}")
        if kept_candidate.logical_view_names:
            lines.append(f"  roots: {', '.join(kept_candidate.logical_view_names)}")
        lines.append(f"  reason: {kept_candidate.reason}")
    return "\n".join(lines)
