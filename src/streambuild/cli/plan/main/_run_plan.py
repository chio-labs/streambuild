"""CLI command for deployment planning."""

import sys
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.main._resolve_default_database import resolve_default_database
from streambuild.cli.plan.main._convert_utc_timestamp_for_clickhouse import (
    convert_utc_timestamp_for_clickhouse,
)
from streambuild.cli.plan.main._normalize_cli_start_time import normalize_cli_start_time
from streambuild.cli.plan.main._source_validation import (
    validate_declared_external_sources,
)
from streambuild.cli.plan.main._warnings import add_empty_replay_source_warnings
from streambuild.cli.plan.main.render_plan_result import render_plan_result
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.models import (
    CompilerAdapterProfile,
    DesiredState,
)
from streambuild.compiler.discovery.models import LoadedPipeline, LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
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


def run_plan(
    *,
    pipelines_root: Path,
    database: str | None,
    selectors: tuple[str, ...],
    full_refresh: bool,
    start_time: str | None,
    json_output: bool,
    verbose: bool,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Plan a staged deployment against live ClickHouse state."""

    try:
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=pipelines_root,
            loaded_project=loaded_project,
            adapter_profile=adapter_profile,
        )
    except TransformSqlContractError as error:
        print(str(error), file=sys.stderr)
        return 1

    if full_refresh and start_time is not None:
        print("--full-refresh cannot be combined with --start-time", file=sys.stderr)
        return 1
    if (full_refresh or start_time is not None) and not selectors:
        required_flag: str = "--full-refresh" if full_refresh else "--start-time"
        print(f"{required_flag} requires at least one --select", file=sys.stderr)
        return 1
    normalized_utc_start_time: str | None = None
    if start_time is not None:
        try:
            normalized_utc_start_time = normalize_cli_start_time(start_time)
        except (CliUserError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1

    loaded_pipelines: tuple[LoadedPipeline, ...] = analysis.compile_inputs.pipelines
    resolved_database: str = resolve_default_database(
        loaded_pipelines=list(loaded_pipelines), override=database
    )
    snapshot: PlanningWarehouseSnapshot = load_planning_warehouse_snapshot(
        client=client,
        database=resolved_database,
    )
    normalized_start_time: str | None = None
    if normalized_utc_start_time is not None:
        try:
            normalized_start_time = convert_utc_timestamp_for_clickhouse(
                timezone_name=snapshot.catalog.warehouse_timezone,
                utc_timestamp=normalized_utc_start_time,
            )
        except (CliUserError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
    validate_declared_external_sources(
        catalog=snapshot.catalog,
        external_source_replay_configs=(
            analysis.realized_project.desired_state.external_source_replay_configs
        ),
        database=resolved_database,
    )
    try:
        selection: SelectionResolution = resolve_selection(
            realized_project=analysis.realized_project,
            graph=analysis.graph,
            selectors=selectors,
        )
    except (CliUserError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    desired_state: DesiredState = selection.desired_state
    actual_state: ActualState = load_actual_state_from_snapshot(
        snapshot=snapshot,
        desired_state=desired_state,
        database=resolved_database,
    )

    plan: DeploymentPlan = plan_deployment(
        desired_state=desired_state,
        actual_state=actual_state,
        default_database=resolved_database,
        render_resource=client.render_resource,
        full_refresh_keys=selection.selected_model_keys if full_refresh else frozenset(),
        start_time_keys=selection.selected_model_keys
        if normalized_start_time is not None
        else frozenset(),
        start_time=normalized_start_time,
    )
    plan = add_empty_replay_source_warnings(
        client=client,
        catalog=snapshot.catalog,
        database=resolved_database,
        desired_state=desired_state,
        plan=plan,
    )
    plan = resolve_unsupported_bounded_replay_behavior(
        catalog=snapshot.catalog,
        deployment_plan=plan,
        desired_state=desired_state,
        default_database=resolved_database,
        replay_lineage_mode=selection.replay_lineage_mode,
    )
    print(
        render_plan_result(
            plan=plan,
            desired_state=desired_state,
            database=resolved_database,
            json_output=json_output,
            verbose=verbose,
        )
    )
    return 0
