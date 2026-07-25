"""CLI command for metadata reconciliation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from streambuild.cli.commands.main.shared.helpers.project import resolve_default_database
from streambuild.cli.commands.main.shared.helpers.selection import resolve_selection
from streambuild.cli.commands.main.shared.models import SelectionResolution
from streambuild.compiler.actual_state.helpers.load import load_actual_state
from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline, DesiredState
from streambuild.compiler.discovery.main import discover_pipelines
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.executor.reconcile.main import execute_reconcile
from streambuild.executor.reconcile.models import (
    ReconcilePreview,
    ReconcileResult,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient


def run_reconcile(
    pipelines_root: Path,
    *,
    database: str | None,
    metadata_database: str | None,
    selectors: tuple[str, ...],
    json_output: bool,
    apply: bool,
    client: ClickHouseClient,
) -> int:
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
    compiled: list[CompiledPipeline] = [compile_pipeline(pipeline) for pipeline in loaded_pipelines]
    resolved_database: str = resolve_default_database(loaded_pipelines, database)
    resolved_metadata_database: str = metadata_database or resolved_database
    selection: SelectionResolution = resolve_selection(tuple(compiled), selectors)
    desired_state: DesiredState = selection.desired_state
    actual_state: ActualState = load_actual_state(
        client=client, desired_state=desired_state, database=resolved_database
    )
    preview: ReconcilePreview = cast(
        ReconcilePreview,
        execute_reconcile(
            client=client,
            metadata_database=resolved_metadata_database,
            desired_state=desired_state,
            actual_state=actual_state,
            selected_model_keys=selection.selected_model_keys,
        ),
    )
    print(_render_reconcile_preview(preview, json_output=json_output))
    if not apply:
        return 0
    if not _confirm_reconcile():
        print("Reconcile cancelled.")
        return 1
    result: ReconcileResult = cast(
        ReconcileResult,
        execute_reconcile(
            client=client,
            metadata_database=resolved_metadata_database,
            desired_state=desired_state,
            actual_state=actual_state,
            selected_model_keys=selection.selected_model_keys,
            apply=True,
        ),
    )
    print(_render_reconcile_result(result, json_output=json_output))
    return 0


def _render_reconcile_preview(preview: ReconcilePreview, *, json_output: bool) -> str:
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


def _render_reconcile_result(result: ReconcileResult, *, json_output: bool) -> str:
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


def _confirm_reconcile() -> bool:
    response: str = input("Proceed with reconcile? [y/N] ").strip().lower()
    return response in {"y", "yes"}
