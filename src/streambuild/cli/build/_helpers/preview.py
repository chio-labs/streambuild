"""Resolve the standard plan a build renders and confirms before it writes."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build.models import BuildCommandOptions, BuildPreviewContext
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.main._resolve_default_database import resolve_default_database
from streambuild.cli.plan.main._source_validation import validate_declared_external_sources
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import CompilerAdapterProfile, LogicalResourceKey
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.main.load_standard_warehouse_snapshot import (
    load_standard_warehouse_snapshot,
)
from streambuild.compiler.planner.main.plan_standard_build import plan_standard_build
from streambuild.compiler.planner.models import StandardPlan, StandardWarehouseSnapshot


def build_standard_build_preview(
    *,
    options: BuildCommandOptions,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> BuildPreviewContext:
    """Compile, resolve the effective mode, and plan the selected closure once."""

    analysis: CompileAnalysis = analyze_project(
        pipelines_root=options.pipelines_root,
        loaded_project=loaded_project,
        adapter_profile=adapter_profile,
    )
    _reject_virtual_environment_project(analysis=analysis)
    database: str = resolve_default_database(
        loaded_pipelines=list(analysis.compile_inputs.pipelines),
        override=options.database,
    )
    metadata_database: str = options.metadata_database or database
    snapshot: StandardWarehouseSnapshot = load_standard_warehouse_snapshot(
        client=client, database=database, metadata_database=metadata_database
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
    plan: StandardPlan = plan_standard_build(
        graph=analysis.graph,
        realized_project=analysis.realized_project,
        snapshot=snapshot,
        database=database,
        selected_model_keys=selected_model_keys,
    )
    return BuildPreviewContext(
        analysis=analysis,
        plan=plan,
        database=database,
        metadata_database=metadata_database,
        adapter_name=client.adapter_identity.name,
    )


def _reject_virtual_environment_project(*, analysis: CompileAnalysis) -> None:
    if analysis.compile_inputs.virtual_environments:
        raise CliUserError(
            "stb build is a standard-mode command and this project enables "
            "settings.virtual_environments. Use stb backfill and stb publish instead."
        )
