from __future__ import annotations

from pathlib import Path

from streambuild.cli.commands.main.backfill.models import BackfillPreviewContext
from streambuild.cli.commands.main.shared._helpers.project import resolve_default_database
from streambuild.cli.commands.main.shared._helpers.selection import resolve_selection
from streambuild.cli.commands.main.shared._helpers.source_validation import (
    validate_declared_external_sources,
)
from streambuild.cli.commands.main.shared._helpers.warnings import add_empty_replay_source_warnings
from streambuild.cli.commands.main.shared.exceptions import CliUserError
from streambuild.cli.commands.main.shared.models import SelectionResolution
from streambuild.compiler.actual_state._helpers.load import load_actual_state
from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline, DesiredState
from streambuild.compiler.discovery.main import discover_pipelines
from streambuild.compiler.planner.main import plan_deployment
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.executor.backfill._helpers.behavior import (
    resolve_unsupported_bounded_replay_behavior,
)
from streambuild.executor.backfill._helpers.reporting import build_root_backfill_reports
from streambuild.executor.backfill.models import RootBackfillReport
from streambuild.integrations.clickhouse.client import ClickHouseClient


def build_backfill_preview_context(
    *,
    pipelines_root: Path,
    database: str | None,
    metadata_database: str | None,
    selectors: tuple[str, ...],
    deployment_id: str | None,
    full_refresh: bool,
    start_time: str | None,
    client: ClickHouseClient,
) -> BackfillPreviewContext:
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
    compiled: list[CompiledPipeline] = [compile_pipeline(pipeline) for pipeline in loaded_pipelines]
    resolved_database: str = resolve_default_database(
        loaded_pipelines=loaded_pipelines, override=database
    )
    validate_declared_external_sources(
        client=client,
        compiled_pipelines=tuple(compiled),
        database=resolved_database,
    )
    resolved_metadata_database: str = metadata_database or resolved_database
    selection: SelectionResolution = resolve_selection(
        compiled_pipelines=tuple(compiled), selectors=selectors
    )
    desired_state: DesiredState = selection.desired_state
    actual_state: ActualState = load_actual_state(
        client=client,
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
    if start_time is not None:
        preview_root_reports: tuple[RootBackfillReport, ...] = build_root_backfill_reports(
            client=client,
            desired_state=desired_state,
            database=resolved_database,
        )
        invalid_root_names: tuple[str, ...] = tuple(
            report.root_key.name
            for report in preview_root_reports
            if report.state_kind != "active_view_present"
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
