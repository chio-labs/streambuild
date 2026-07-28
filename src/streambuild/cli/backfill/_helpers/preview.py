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
from streambuild.compiler.compile.models import (
    CompilerAdapterProfile,
    DesiredState,
)
from streambuild.compiler.discovery.models import LoadedPipeline, LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.main.assert_no_standard_owned_targets import (
    assert_no_standard_owned_targets,
)
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
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> BackfillPreviewContext:
    analysis: CompileAnalysis = analyze_project(
        pipelines_root=pipelines_root,
        loaded_project=loaded_project,
        adapter_profile=adapter_profile,
    )
    loaded_pipelines: tuple[LoadedPipeline, ...] = analysis.compile_inputs.pipelines
    resolved_database: str = resolve_default_database(
        loaded_pipelines=list(loaded_pipelines), override=database
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
        external_source_replay_configs=(
            analysis.realized_project.desired_state.external_source_replay_configs
        ),
        database=resolved_database,
    )
    resolved_metadata_database: str = metadata_database or resolved_database
    selection: SelectionResolution = resolve_selection(
        realized_project=analysis.realized_project,
        graph=analysis.graph,
        selectors=selectors,
    )
    desired_state: DesiredState = selection.desired_state
    assert_no_standard_owned_targets(
        client=client,
        database=resolved_metadata_database,
        relation_names=tuple(object_.name for object_ in desired_state.objects),
    )
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
