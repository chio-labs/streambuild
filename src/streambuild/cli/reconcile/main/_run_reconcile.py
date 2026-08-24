"""CLI command for metadata reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.entry.main._resolve_default_database import resolve_default_database
from streambuild.cli.reconcile._helpers.rendering import (
    confirm_reconcile,
    render_reconcile_preview,
    render_reconcile_result,
)
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import (
    CompilerAdapterProfile,
    DesiredState,
)
from streambuild.compiler.discovery.models import LoadedPipeline, LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.main.load_actual_state import load_actual_state
from streambuild.compiler.planner.models import ActualState
from streambuild.executor.reconcile.main.execute_reconcile import execute_reconcile
from streambuild.executor.reconcile.models import (
    ReconcilePreview,
    ReconcileResult,
)


def run_reconcile(
    *,
    pipelines_root: Path,
    database: str | None,
    metadata_database: str | None,
    selectors: tuple[str, ...],
    json_output: bool,
    apply: bool,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    analysis: CompileAnalysis = analyze_project(
        pipelines_root=pipelines_root,
        loaded_project=loaded_project,
        adapter_profile=adapter_profile,
    )
    loaded_pipelines: tuple[LoadedPipeline, ...] = analysis.compile_inputs.pipelines
    resolved_database: str = resolve_default_database(
        loaded_pipelines=list(loaded_pipelines), override=database
    )
    resolved_metadata_database: str = metadata_database or resolved_database
    selection: SelectionResolution = resolve_selection(
        realized_project=analysis.realized_project,
        graph=analysis.graph,
        selectors=selectors,
    )
    desired_state: DesiredState = selection.desired_state
    actual_state: ActualState = load_actual_state(
        client=client, desired_state=desired_state, database=resolved_database
    )
    preview: ReconcilePreview = cast(
        ReconcilePreview,
        execute_reconcile(
            client=client,
            target_database=resolved_database,
            metadata_database=resolved_metadata_database,
            desired_state=desired_state,
            actual_state=actual_state,
            selected_model_keys=selection.selected_model_keys,
        ),
    )
    print(render_reconcile_preview(preview=preview, json_output=json_output))
    if not apply:
        return 0
    if not confirm_reconcile():
        print("Reconcile cancelled.")
        return 1
    result: ReconcileResult = cast(
        ReconcileResult,
        execute_reconcile(
            client=client,
            target_database=resolved_database,
            metadata_database=resolved_metadata_database,
            desired_state=desired_state,
            actual_state=actual_state,
            selected_model_keys=selection.selected_model_keys,
            apply=True,
        ),
    )
    print(render_reconcile_result(result=result, json_output=json_output))
    return 0
