"""Execute `stb plan` for a project whose effective mode is direct."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.plan._helpers.direct_rendering import (
    render_direct_plan_json,
    render_direct_plan_text,
)
from streambuild.cli.plan.main._source_validation import validate_declared_external_sources
from streambuild.cli.plan.models import PlanCommandOptions, PlanCommandResult
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.main.load_direct_warehouse_snapshot import (
    load_direct_warehouse_snapshot,
)
from streambuild.compiler.planner.main.plan_direct_build import plan_direct_build
from streambuild.compiler.planner.models import DirectPlan, DirectWarehouseSnapshot


def execute_direct_plan(
    *,
    analysis: CompileAnalysis,
    options: PlanCommandOptions,
    client: AdapterConnection,
) -> PlanCommandResult:
    """Plan the complete selected downstream closure and render it."""

    snapshot: DirectWarehouseSnapshot = load_direct_warehouse_snapshot(
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
    plan: DirectPlan = plan_direct_build(
        graph=analysis.graph,
        realized_project=analysis.realized_project,
        snapshot=snapshot,
        database=options.database,
        selected_model_keys=selected_model_keys,
    )
    adapter_name: str = client.adapter_identity.name
    serialized_plan: str = render_direct_plan_json(plan=plan, adapter_name=adapter_name)
    rendered_output: str = (
        serialized_plan
        if options.json_output
        else render_direct_plan_text(plan=plan, adapter_name=adapter_name) + "\n"
    )
    return PlanCommandResult(rendered_output=rendered_output, serialized_plan=serialized_plan)
