"""Execute `stb plan` for a project whose effective mode is virtual environments."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.plan._helpers.result_rendering import render_plan_json
from streambuild.cli.plan.main._convert_utc_timestamp_for_clickhouse import (
    convert_utc_timestamp_for_clickhouse,
)
from streambuild.cli.plan.main._source_validation import validate_declared_external_sources
from streambuild.cli.plan.main._warnings import add_empty_replay_source_warnings
from streambuild.cli.plan.main.render_plan_result import render_plan_result
from streambuild.cli.plan.models import PlanCommandOptions, PlanCommandResult
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.main.load_actual_state_from_snapshot import (
    load_actual_state_from_snapshot,
)
from streambuild.compiler.planner.main.load_planning_warehouse_snapshot import (
    load_planning_warehouse_snapshot,
)
from streambuild.compiler.planner.main.plan_deployment import plan_deployment
from streambuild.compiler.planner.models import (
    ActualState,
    DeploymentPlan,
    PlanningWarehouseSnapshot,
)
from streambuild.executor.backfill.main.resolve_unsupported_bounded_replay_behavior import (
    resolve_unsupported_bounded_replay_behavior,
)


def execute_virtual_environment_plan(
    *,
    analysis: CompileAnalysis,
    options: PlanCommandOptions,
    client: AdapterConnection,
    normalized_utc_start_time: str | None,
) -> PlanCommandResult:
    """Preserve the staged deployment plan exactly as previously rendered."""

    snapshot: PlanningWarehouseSnapshot = load_planning_warehouse_snapshot(
        client=client,
        database=options.database,
    )
    normalized_start_time: str | None = _local_start_time(
        snapshot=snapshot, normalized_utc_start_time=normalized_utc_start_time
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
    replay_lineage_mode: ReplayLineageMode = (
        selection.replay_lineage_mode or ReplayLineageMode.OFFSETS
    )
    desired_state: DesiredState = selection.desired_state
    actual_state: ActualState = load_actual_state_from_snapshot(
        snapshot=snapshot,
        desired_state=desired_state,
        database=options.database,
    )
    plan: DeploymentPlan = plan_deployment(
        desired_state=desired_state,
        actual_state=actual_state,
        default_database=options.database,
        render_resource=client.render_resource,
        full_refresh_keys=selection.selected_model_keys if options.full_refresh else frozenset(),
        start_time_keys=(
            selection.selected_model_keys if normalized_start_time is not None else frozenset()
        ),
        start_time=normalized_start_time,
    )
    plan = add_empty_replay_source_warnings(
        client=client,
        catalog=snapshot.catalog,
        database=options.database,
        desired_state=desired_state,
        plan=plan,
    )
    plan = resolve_unsupported_bounded_replay_behavior(
        catalog=snapshot.catalog,
        deployment_plan=plan,
        desired_state=desired_state,
        default_database=options.database,
        replay_lineage_mode=replay_lineage_mode,
    )
    adapter_name: str = client.adapter_identity.name
    serialized_plan: str = render_plan_json(plan=plan, adapter_name=adapter_name)
    rendered_output: str = (
        serialized_plan
        if options.json_output
        else render_plan_result(
            plan=plan,
            desired_state=desired_state,
            database=options.database,
            adapter_name=adapter_name,
            json_output=False,
            verbose=options.verbose,
        )
        + "\n"
    )
    return PlanCommandResult(rendered_output=rendered_output, serialized_plan=serialized_plan)


def _local_start_time(
    *, snapshot: PlanningWarehouseSnapshot, normalized_utc_start_time: str | None
) -> str | None:
    if normalized_utc_start_time is None:
        return None
    return convert_utc_timestamp_for_clickhouse(
        timezone_name=snapshot.catalog.warehouse_timezone,
        utc_timestamp=normalized_utc_start_time,
    )
