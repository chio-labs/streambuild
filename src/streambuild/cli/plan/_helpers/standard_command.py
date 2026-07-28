"""Execute `stb plan` for a project whose effective mode is standard."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.plan._helpers.standard_rendering import (
    render_standard_plan_json,
    render_standard_plan_text,
)
from streambuild.cli.plan.main._source_validation import validate_declared_external_sources
from streambuild.cli.plan.models import PlanCommandOptions
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.main.load_standard_warehouse_snapshot import (
    load_standard_warehouse_snapshot,
)
from streambuild.compiler.planner.main.plan_standard_build import plan_standard_build
from streambuild.compiler.planner.models import StandardPlan, StandardWarehouseSnapshot


def execute_standard_plan(
    *,
    analysis: CompileAnalysis,
    options: PlanCommandOptions,
    client: AdapterConnection,
) -> str:
    """Plan the complete selected downstream closure and render it."""

    snapshot: StandardWarehouseSnapshot = load_standard_warehouse_snapshot(
        client=client,
        database=options.database,
        metadata_database=options.database,
    )
    validate_declared_external_sources(
        catalog=snapshot.catalog,
        external_source_replay_configs=(
            analysis.realized_project.desired_state.external_source_replay_configs
        ),
        database=options.database,
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
        database=options.database,
        selected_model_keys=selected_model_keys,
    )
    adapter_name: str = client.adapter_identity.name
    if options.json_output:
        return render_standard_plan_json(plan=plan, adapter_name=adapter_name)
    return render_standard_plan_text(plan=plan, adapter_name=adapter_name)
