"""Resolve the direct plan a build renders and confirms before it writes."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterDirectFingerprintRecord
from streambuild.adapter.types import AdapterOptionalStateStatus
from streambuild.cli.build.models import DirectBuildPreviewContext, WorkflowPreparationOptions
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.main._resolve_default_database import resolve_default_database
from streambuild.cli.plan.main._source_validation import validate_declared_external_sources
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import CompiledTableModel, LogicalResourceKey
from streambuild.compiler.discovery.models import PostgresRefreshSourceStep
from streambuild.compiler.discovery.types import PipelineMode
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.classes.direct_model_fingerprint import DirectModelFingerprint
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.compiler.planner.main.load_direct_warehouse_snapshot import (
    load_direct_warehouse_snapshot,
)
from streambuild.compiler.planner.main.plan_direct_build import plan_direct_build
from streambuild.compiler.planner.models import DirectPlan, DirectWarehouseSnapshot
from streambuild.compiler.planner.types import DirectSelectionMode


def build_direct_build_preview(
    *,
    options: WorkflowPreparationOptions,
    client: AdapterConnection,
    analysis: CompileAnalysis,
    effective_start_time: str | None = None,
) -> DirectBuildPreviewContext:
    """Plan the selected direct closure from one shared compile analysis."""
    database: str = resolve_default_database(
        loaded_pipelines=list(analysis.compile_inputs.pipelines),
        override=options.database,
    )
    metadata_database: str = options.metadata_database or database
    snapshot: DirectWarehouseSnapshot = load_direct_warehouse_snapshot(
        client=client,
        database=database,
        metadata_database=metadata_database,
        logical_model_identities=tuple(
            f"{database}.{model.key.name}" for model in analysis.realized_project.project.models
        ),
    )
    start_time: str | None = effective_start_time
    validate_declared_external_sources(
        catalog=snapshot.catalog,
        external_source_replay_configs=(
            analysis.realized_project.desired_state.external_source_replay_configs
        ),
        database=database,
    )
    selection_mode: DirectSelectionMode
    selected_model_keys: frozenset[LogicalResourceKey]
    if options.changed:
        selection_mode = DirectSelectionMode.CHANGED
        selected_model_keys = _changed_direct_model_keys(
            analysis=analysis,
            snapshot=snapshot,
            database=database,
        )
        _reject_changed_replayless_start_time(
            analysis=analysis,
            selected_model_keys=selected_model_keys,
            start_time=options.start_time,
        )
    else:
        selection: SelectionResolution = resolve_selection(
            realized_project=analysis.realized_project,
            graph=analysis.graph,
            selectors=options.selectors,
        )
        selected_model_keys = selection.selected_logical_model_keys
        selection_mode = (
            DirectSelectionMode.EXPLICIT if options.selectors else DirectSelectionMode.ALL_MODELS
        )
    plan: DirectPlan = plan_direct_build(
        graph=analysis.graph,
        realized_project=analysis.realized_project,
        snapshot=snapshot,
        database=database,
        selected_model_keys=selected_model_keys,
        selection_mode=selection_mode,
        include_missing_upstream=options.include_missing_upstream,
        effective_start_time=start_time,
    )
    return DirectBuildPreviewContext(
        analysis=analysis,
        plan=plan,
        warehouse_snapshot=snapshot,
        database=database,
        metadata_database=metadata_database,
        adapter_name=client.adapter_identity.name,
        effective_start_time=start_time,
    )


def _changed_direct_model_keys(
    *, analysis: CompileAnalysis, snapshot: DirectWarehouseSnapshot, database: str
) -> frozenset[LogicalResourceKey]:
    if snapshot.fingerprints.status == AdapterOptionalStateStatus.UNAVAILABLE:
        detail: str = snapshot.fingerprints.warning or "direct fingerprints are unavailable"
        raise DirectPlanError(f"Cannot select changed models: {detail}")
    direct_model_key_set: set[LogicalResourceKey] = set()
    for pipeline in analysis.compiled_project.pipelines:
        if PipelineMode(pipeline.pipeline.mode) == PipelineMode.DIRECT:
            direct_model_key_set.update(model.key for model in pipeline.models)
    direct_model_keys: frozenset[LogicalResourceKey] = frozenset(direct_model_key_set)
    if not direct_model_keys:
        raise DirectPlanError("--changed is only supported for direct models")
    baseline_by_identity: dict[str, AdapterDirectFingerprintRecord] = {
        baseline.logical_model_identity: baseline for baseline in snapshot.fingerprints.baselines
    }
    return frozenset(
        model.key
        for model in analysis.compiled_project.models
        if model.key in direct_model_keys
        and DirectModelFingerprint.drift_reasons(
            model=model,
            realized_project=analysis.realized_project,
            baseline=baseline_by_identity.get(f"{database}.{model.key.name}"),
        )
    )


def _reject_changed_replayless_start_time(
    *,
    analysis: CompileAnalysis,
    selected_model_keys: frozenset[LogicalResourceKey],
    start_time: str | None,
) -> None:
    if start_time is None or not selected_model_keys:
        return
    postgres_source_names: frozenset[str] = frozenset(
        source.key.name
        for source in analysis.compiled_project.sources
        if isinstance(source.source, PostgresRefreshSourceStep)
    )
    replayless_names: tuple[str, ...] = tuple(
        sorted(
            model.key.name
            for model in analysis.compiled_project.models
            if model.key in selected_model_keys
            and isinstance(model, CompiledTableModel)
            and model.transform.source in postgres_source_names
        )
    )
    if replayless_names and len(replayless_names) == len(selected_model_keys):
        raise CliUserError(
            "--start-time is not available for scheduled postgres sources, which the "
            f"warehouse refreshes in full: {', '.join(replayless_names)}"
        )
