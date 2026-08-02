"""Resolve the direct plan a build renders and confirms before it writes."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build.models import DirectBuildPreviewContext, WorkflowPreparationOptions
from streambuild.cli.entry.main._resolve_default_database import resolve_default_database
from streambuild.cli.plan.main._convert_utc_timestamp_for_clickhouse import (
    convert_utc_timestamp_for_clickhouse,
)
from streambuild.cli.plan.main._source_validation import validate_declared_external_sources
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.main.load_direct_warehouse_snapshot import (
    load_direct_warehouse_snapshot,
)
from streambuild.compiler.planner.main.plan_direct_build import plan_direct_build
from streambuild.compiler.planner.models import DirectPlan, DirectWarehouseSnapshot


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
        client=client, database=database, metadata_database=metadata_database
    )
    start_time: str | None = (
        convert_utc_timestamp_for_clickhouse(
            timezone_name=snapshot.catalog.warehouse_timezone,
            utc_timestamp=effective_start_time,
        )
        if effective_start_time is not None
        else None
    )
    validate_declared_external_sources(
        catalog=snapshot.catalog,
        external_source_replay_configs=(
            analysis.realized_project.desired_state.external_source_replay_configs
        ),
        database=database,
    )
    selection: SelectionResolution = resolve_selection(
        realized_project=analysis.realized_project,
        graph=analysis.graph,
        selectors=options.selectors,
    )
    selected_model_keys: frozenset[LogicalResourceKey] = selection.selected_logical_model_keys
    plan: DirectPlan = plan_direct_build(
        graph=analysis.graph,
        realized_project=analysis.realized_project,
        snapshot=snapshot,
        database=database,
        selected_model_keys=selected_model_keys,
        effective_start_time=start_time,
    )
    return DirectBuildPreviewContext(
        analysis=analysis,
        plan=plan,
        database=database,
        metadata_database=metadata_database,
        adapter_name=client.adapter_identity.name,
        effective_start_time=start_time,
    )
