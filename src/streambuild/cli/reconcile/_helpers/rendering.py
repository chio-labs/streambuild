"""Reconcile preview and result rendering."""

from __future__ import annotations

import json

from streambuild.cli.entry.constants import AFFIRMATIVE_RESPONSES
from streambuild.executor.reconcile.models import (
    ReconcilePreview,
    ReconcileResult,
)


def render_reconcile_preview(*, preview: ReconcilePreview, json_output: bool) -> str:
    if json_output:
        return json.dumps(
            {
                "database": preview.database,
                "reconcile_id": preview.reconcile_id,
                "eligible_target_names": sorted(
                    {record.key.name for record in preview.eligible_records}
                ),
                "rejected_targets": [
                    {
                        "target_name": target.target_name,
                        "reasons": list(target.reasons),
                    }
                    for target in preview.rejected_targets
                ],
            }
        )
    lines: list[str] = [f"Reconcile Preview\nDatabase: {preview.database}"]
    eligible_target_names: tuple[str, ...] = tuple(
        sorted({record.key.name for record in preview.eligible_records})
    )
    lines.append(f"Eligible targets: {len(eligible_target_names)}")
    for target_name in eligible_target_names:
        lines.append(f"- {target_name}")
    if preview.rejected_targets:
        lines.append("Rejected targets:")
        for rejected in preview.rejected_targets:
            lines.append(f"- {rejected.target_name}: {', '.join(rejected.reasons)}")
    return "\n".join(lines)


def render_reconcile_result(*, result: ReconcileResult, json_output: bool) -> str:
    if json_output:
        return json.dumps(
            {
                "database": result.database,
                "reconcile_id": result.reconcile_id,
                "reconciled_target_names": sorted(
                    {record.key.name for record in result.reconciled_records}
                ),
                "rejected_targets": [
                    {
                        "target_name": target.target_name,
                        "reasons": list(target.reasons),
                    }
                    for target in result.rejected_targets
                ],
            }
        )
    return (
        "Reconcile Applied\n"
        f"Database: {result.database}\n"
        f"Reconcile id: {result.reconcile_id}\n"
        f"Reconciled targets: {len({record.key.name for record in result.reconciled_records})}"
    )


def confirm_reconcile() -> bool:
    response: str = input("Proceed with reconcile? [y/N] ").strip().lower()
    return response in AFFIRMATIVE_RESPONSES
