from __future__ import annotations

from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.backfill.models import BackfillPreviewContext
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.main._resolve_default_database import resolve_default_database
from streambuild.cli.plan.main._convert_utc_timestamp_for_clickhouse import (
    convert_utc_timestamp_for_clickhouse,
)
from streambuild.cli.plan.main._source_validation import (
    validate_declared_external_sources,
)
from streambuild.cli.plan.main._warnings import add_empty_replay_source_warnings
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline, DesiredState
from streambuild.compiler.discovery.main.discover_pipelines import discover_pipelines
from streambuild.compiler.discovery.models import LoadedPipeline
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
from streambuild.compiler.planner.types import RootDeploymentStateKind
from streambuild.executor.backfill.main.build_root_backfill_reports import (
    build_root_backfill_reports,
)
from streambuild.executor.backfill.main.resolve_unsupported_bounded_replay_behavior import (
    resolve_unsupported_bounded_replay_behavior,
)
from streambuild.executor.backfill.models import RootBackfillReport


def build_backfill_preview_context(
    *,
    pipelines_root: Path,
    database: str | None,
    metadata_database: str | None,
    selectors: tuple[str, ...],
    deployment_id: str | None,
    full_refresh: bool,
    start_time_utc: str | None,
    client: AdapterConnection,
) -> BackfillPreviewContext:
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
    compiled: list[CompiledPipeline] = [compile_pipeline(pipeline) for pipeline in loaded_pipelines]
    resolved_database: str = resolve_default_database(
        loaded_pipelines=loaded_pipelines, override=database
    )
    snapshot: PlanningWarehouseSnapshot = load_planning_warehouse_snapshot(
        client=client,
        database=resolved_database,
    )
    start_time: str | None = (
        convert_utc_timestamp_for_clickhouse(
            timezone_name=snapshot.catalog.warehouse_timezone,
            utc_timestamp=start_time_utc,
        )
        if start_time_utc is not None
        else None
    )
    validate_declared_external_sources(
        catalog=snapshot.catalog,
        compiled_pipelines=tuple(compiled),
        database=resolved_database,
    )
    resolved_metadata_database: str = metadata_database or resolved_database
    selection: SelectionResolution = resolve_selection(
        compiled_pipelines=tuple(compiled), selectors=selectors
    )
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
        deployment_id=deployment_id,
        full_refresh_keys=selection.selected_model_keys if full_refresh else frozenset(),
        start_time_keys=selection.selected_model_keys if start_time is not None else frozenset(),
        start_time=start_time,
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
    if start_time is not None:
        preview_root_reports: tuple[RootBackfillReport, ...] = build_root_backfill_reports(
            catalog=snapshot.catalog,
            desired_state=desired_state,
        )
        invalid_root_names: tuple[str, ...] = tuple(
            report.root_key.name
            for report in preview_root_reports
            if report.state_kind != RootDeploymentStateKind.ACTIVE_VIEW_PRESENT
        )
        if invalid_root_names:
            root_name_list: str = ", ".join(sorted(invalid_root_names))
            raise CliUserError(
                "--start-time requires an active published root for every selected target; "
                f"found unsupported state for {root_name_list}"
            )
    return BackfillPreviewContext(
        resolved_database=resolved_database,
        resolved_metadata_database=resolved_metadata_database,
        desired_state=desired_state,
        plan=plan,
        replay_lineage_mode=selection.replay_lineage_mode,
        full_refresh_keys=selection.selected_model_keys if full_refresh else frozenset(),
        start_time_keys=selection.selected_model_keys if start_time is not None else frozenset(),
        start_time=start_time,
    )
