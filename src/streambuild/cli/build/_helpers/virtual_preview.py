from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import CatalogSnapshot
from streambuild.cli.build.models import (
    VirtualBuildPreviewContext,
    WorkflowPreparationOptions,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.main._resolve_default_database import resolve_default_database
from streambuild.cli.plan.main._source_validation import (
    validate_declared_external_sources,
)
from streambuild.cli.plan.main._warnings import add_empty_replay_source_warnings
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.discovery.models import LoadedPipeline
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
from streambuild.compiler.planner.types import RootDeploymentStateKind
from streambuild.executor.backfill.main.build_backfill_deployment_identity import (
    build_backfill_deployment_identity,
)
from streambuild.executor.backfill.main.build_root_backfill_reports import (
    build_root_backfill_reports,
)
from streambuild.executor.backfill.main.resolve_unsupported_bounded_replay_behavior import (
    resolve_unsupported_bounded_replay_behavior,
)
from streambuild.executor.backfill.models import BackfillDeploymentIdentity, RootBackfillReport


def build_virtual_build_preview(
    *,
    options: WorkflowPreparationOptions,
    start_time_utc: str | None,
    client: AdapterConnection,
    analysis: CompileAnalysis,
) -> VirtualBuildPreviewContext:
    loaded_pipelines: tuple[LoadedPipeline, ...] = analysis.compile_inputs.pipelines
    resolved_database: str = resolve_default_database(
        loaded_pipelines=list(loaded_pipelines), override=options.database
    )
    snapshot: PlanningWarehouseSnapshot = load_planning_warehouse_snapshot(
        client=client,
        database=resolved_database,
    )
    start_time: str | None = start_time_utc
    validate_declared_external_sources(
        catalog=snapshot.catalog,
        external_source_replay_configs=(
            analysis.realized_project.desired_state.external_source_replay_configs
        ),
        database=resolved_database,
    )
    resolved_metadata_database: str = options.metadata_database or resolved_database
    metadata_catalog: CatalogSnapshot = (
        snapshot.catalog
        if resolved_metadata_database == resolved_database
        else client.load_catalog(resolved_metadata_database)
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
        database=resolved_database,
    )
    deployment_identity: BackfillDeploymentIdentity = build_backfill_deployment_identity(
        deployment_id=options.deployment_id
    )
    plan: DeploymentPlan = plan_deployment(
        desired_state=desired_state,
        actual_state=actual_state,
        default_database=resolved_database,
        render_resource=client.render_resource,
        deployment_id=deployment_identity.deployment_id,
        full_refresh_keys=selection.selected_model_keys if options.full_refresh else frozenset(),
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
        replay_lineage_mode=replay_lineage_mode,
    )
    preview_root_reports: tuple[RootBackfillReport, ...] = build_root_backfill_reports(
        catalog=snapshot.catalog,
        desired_state=desired_state,
    )
    if start_time is not None:
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
    return VirtualBuildPreviewContext(
        database=resolved_database,
        metadata_database=resolved_metadata_database,
        desired_state=desired_state,
        plan=plan,
        replay_lineage_mode=replay_lineage_mode,
        deployment_id=deployment_identity.deployment_id,
        created_at=deployment_identity.created_at,
        root_reports=preview_root_reports,
        existing_relation_names=snapshot.catalog.relation_names(),
        target_catalog=snapshot.catalog,
        metadata_catalog=metadata_catalog,
        full_refresh_keys=(selection.selected_model_keys if options.full_refresh else frozenset()),
        start_time_keys=selection.selected_model_keys if start_time is not None else frozenset(),
        start_time=start_time,
        execution_logical_model_keys=selection.execution_logical_model_keys,
    )
