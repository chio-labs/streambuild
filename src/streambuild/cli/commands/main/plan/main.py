"""CLI command for deployment planning."""

import sys
from pathlib import Path

from streambuild.cli.commands.main.shared.helpers.plan_rendering import render_plan_result
from streambuild.cli.commands.main.shared.helpers.project import resolve_default_database
from streambuild.cli.commands.main.shared.helpers.selection import resolve_selection
from streambuild.cli.commands.main.shared.helpers.source_validation import (
    validate_declared_external_sources,
)
from streambuild.cli.commands.main.shared.helpers.timestamps import (
    convert_utc_timestamp_for_clickhouse,
    normalize_cli_start_time,
)
from streambuild.cli.commands.main.shared.helpers.warnings import add_empty_replay_source_warnings
from streambuild.cli.commands.main.shared.models import SelectionResolution
from streambuild.compiler.actual_state.helpers.load import load_actual_state
from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline, DesiredState
from streambuild.compiler.discovery.main import discover_pipelines
from streambuild.compiler.planner.main import plan_deployment
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.executor.backfill.helpers.behavior import (
    resolve_unsupported_bounded_replay_behavior,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient


def run_plan(
    pipelines_root: Path,
    *,
    database: str | None,
    selectors: tuple[str, ...],
    full_refresh: bool,
    start_time: str | None,
    json_output: bool,
    verbose: bool,
    client: ClickHouseClient,
) -> int:
    """Plan a staged deployment against live ClickHouse state."""

    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)

    try:
        compiled: list[CompiledPipeline] = [
            compile_pipeline(pipeline) for pipeline in loaded_pipelines
        ]
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
    normalized_start_time: str | None = None
    if start_time is not None:
        try:
            normalized_start_time = convert_utc_timestamp_for_clickhouse(
                client,
                normalize_cli_start_time(start_time),
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1

    resolved_database: str = resolve_default_database(loaded_pipelines, database)
    validate_declared_external_sources(
        client=client,
        compiled_pipelines=tuple(compiled),
        database=resolved_database,
    )
    try:
        selection: SelectionResolution = resolve_selection(tuple(compiled), selectors)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    desired_state: DesiredState = selection.desired_state
    actual_state: ActualState = load_actual_state(
        client=client,
        desired_state=desired_state,
        database=resolved_database,
    )

    plan: DeploymentPlan = plan_deployment(
        desired_state,
        actual_state,
        default_database=resolved_database,
        full_refresh_keys=selection.selected_model_keys if full_refresh else frozenset(),
        start_time_keys=selection.selected_model_keys
        if normalized_start_time is not None
        else frozenset(),
        start_time=normalized_start_time,
    )
    plan = add_empty_replay_source_warnings(
        client=client,
        database=resolved_database,
        desired_state=desired_state,
        plan=plan,
    )
    plan = resolve_unsupported_bounded_replay_behavior(
        client=client,
        deployment_plan=plan,
        desired_state=desired_state,
        default_database=resolved_database,
        replay_lineage_mode=selection.replay_lineage_mode,
    )
    print(
        render_plan_result(
            plan,
            desired_state=desired_state,
            database=resolved_database,
            json_output=json_output,
            verbose=verbose,
        )
    )
    return 0
