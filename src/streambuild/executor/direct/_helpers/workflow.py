"""Assemble the complete authoritative direct build workflow."""

from __future__ import annotations

import math
from dataclasses import replace

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterCapturedReplayRequest,
    AdapterMaterializedView,
    AdapterReplayBoundary,
    AdapterReplayCoverageRequest,
    AdapterReplayLowerBound,
    AdapterReplayOffsetProgressRequest,
    AdapterReplayOffsetRange,
    AdapterReplayRequest,
    CatalogRelation,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    DesiredView,
    ObjectKey,
)
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource
from streambuild.compiler.planner.models import (
    DirectPlanEntry,
    DirectRelationOperation,
    DirectWarehouseSnapshot,
)
from streambuild.compiler.planner.types import DirectResourceKind
from streambuild.executor.auditing.constants import AUDIT_SAMPLE_LIMIT
from streambuild.executor.direct._helpers.population_plan import build_direct_population_plan
from streambuild.executor.direct._helpers.preflight import reject_incapable_adapter
from streambuild.executor.direct._helpers.sources import plan_preserved_managed_sources
from streambuild.executor.direct.exceptions import DirectBuildError
from streambuild.executor.direct.models import (
    DirectBuildAudit,
    DirectBuildRequest,
    DirectBuildWorkflow,
    DirectReplayCapture,
    DirectReplayRange,
    DirectRuntimeReplay,
)
from streambuild.executor.population.main._build_population_replay_templates import (
    build_population_replay_templates,
)
from streambuild.executor.population.main._expand_population_plan import expand_population_plan
from streambuild.executor.population.main._plan_population_objects import plan_population_objects
from streambuild.executor.population.models import (
    PopulationPlan,
    PopulationRealization,
    PopulationSourcePreparation,
)
from streambuild.executor.workflow.models import BuildWorkflow, WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowMode, WorkflowPhase


def assemble_direct_build_workflow(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    snapshot: DirectWarehouseSnapshot,
    plan_json: str,
) -> DirectBuildWorkflow:
    """Resolve preconditions and assemble every direct lifecycle statement once."""

    reject_incapable_adapter(client=client)
    source_preparation: PopulationSourcePreparation
    source_realizations: tuple[PopulationRealization, ...]
    source_preparation, source_realizations = plan_preserved_managed_sources(
        plan=request.plan,
        realized_project=request.realized_project,
        catalog=snapshot.catalog,
        database=request.database,
    )
    preserved_landing_views: tuple[DesiredMaterializedView, ...] = tuple(
        desired
        for desired in request.realized_project.desired_state.objects
        if isinstance(desired, DesiredMaterializedView)
        and desired.name in source_preparation.preserved_relation_names
    )
    population_plan: PopulationPlan = expand_population_plan(
        plan=build_direct_population_plan(
            plan=request.plan,
            realized_project=request.realized_project,
        ),
        desired_state=request.realized_project.desired_state,
    )
    realizations: tuple[PopulationRealization, ...] = plan_population_objects(
        plan=population_plan,
        desired_state=request.realized_project.desired_state,
        default_database=request.database,
    )
    replay_template_pairs: tuple[tuple[ObjectKey, AdapterReplayRequest], ...] = (
        build_population_replay_templates(
            plan=population_plan,
            desired_state=request.realized_project.desired_state,
            default_database=request.database,
        )
    )
    replay_templates: tuple[AdapterReplayRequest, ...] = tuple(
        template for _key, template in replay_template_pairs
    )
    replay_by_model_name: dict[str, AdapterReplayRequest] = {
        _model_name_for_target(request=request, target=replay.relations.target): replay
        for replay in replay_templates
    }
    _assert_bounded_replay_inputs(
        request=request,
        snapshot=snapshot,
        replay_by_model_name=replay_by_model_name,
    )
    runtime_replays: tuple[DirectRuntimeReplay, ...] = _runtime_replays(
        request=request,
        snapshot=snapshot,
        replay_templates=replay_templates,
    )
    statements: tuple[WarehouseStatement, ...] = _assemble_statements(
        request=request,
        client=client,
        source_preparation=source_preparation,
        source_realizations=source_realizations,
        preserved_landing_views=preserved_landing_views,
        realizations=realizations,
        runtime_replays=runtime_replays,
    )
    paused_landing_views: tuple[DesiredMaterializedView, ...] = (
        *preserved_landing_views,
        *source_preparation.landing_views,
    )
    source_recovery_statements: tuple[WarehouseStatement, ...] = _source_recovery_statements(
        statements=statements,
        landing_view_names=tuple(landing_view.name for landing_view in paused_landing_views),
    )
    return DirectBuildWorkflow(
        template=BuildWorkflow(
            mode=WorkflowMode.DIRECT,
            plan_json=plan_json,
            statements=statements,
        ),
        runtime_replays=runtime_replays,
        workflow_id=request.workflow_id,
        source_recovery_statements=source_recovery_statements,
    )


def _assemble_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    source_preparation: PopulationSourcePreparation,
    source_realizations: tuple[PopulationRealization, ...],
    preserved_landing_views: tuple[DesiredMaterializedView, ...],
    realizations: tuple[PopulationRealization, ...],
    runtime_replays: tuple[DirectRuntimeReplay, ...],
) -> tuple[WarehouseStatement, ...]:
    if not request.plan.execution_scope and not request.audits:
        return ()
    rendered_realizations: tuple[tuple[PopulationRealization, str], ...] = tuple(
        (
            realization,
            _terminate_sql(
                client.render_resource(
                    resource=realization.resource,
                    database=realization.database,
                )
            ),
        )
        for realization in realizations
    )
    preserved_landing_view_names: tuple[str, ...] = tuple(
        landing_view.name for landing_view in preserved_landing_views
    )
    preparation: tuple[WarehouseStatement, ...] = _preparation_statements(
        request=request,
        client=client,
        source_preparation=source_preparation,
        source_realizations=source_realizations,
        preserved_landing_view_names=preserved_landing_view_names,
        start_sequence=1,
    )
    teardown: tuple[WarehouseStatement, ...] = _teardown_statements(
        request=request,
        start_sequence=len(preparation) + 1,
    )
    realization: tuple[WarehouseStatement, ...] = _realization_statements(
        rendered_realizations=rendered_realizations,
        start_sequence=len(preparation) + len(teardown) + 1,
    )
    stabilization: tuple[WarehouseStatement, ...] = _stabilization_statements(
        seconds=request.stabilization_seconds,
        start_sequence=(len(preparation) + len(teardown) + len(realization) + 1),
    )
    prior_count: int = sum(
        len(phase) for phase in (preparation, teardown, realization, stabilization)
    )
    replay: tuple[WarehouseStatement, ...] = _runtime_replay_statements(
        client=client,
        runtime_replays=runtime_replays,
        start_sequence=prior_count + 1,
    )
    activation: tuple[WarehouseStatement, ...] = _source_activation_statements(
        request=request,
        client=client,
        source_preparation=source_preparation,
        preserved_landing_views=preserved_landing_views,
        start_sequence=prior_count + len(replay) + 1,
    )
    audit: tuple[WarehouseStatement, ...] = _audit_statements(
        audits=request.audits,
        start_sequence=prior_count + len(replay) + len(activation) + 1,
    )
    return (
        *preparation,
        *teardown,
        *realization,
        *stabilization,
        *replay,
        *activation,
        *audit,
    )


def _preparation_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    source_preparation: PopulationSourcePreparation,
    source_realizations: tuple[PopulationRealization, ...],
    preserved_landing_view_names: tuple[str, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    passive_rendered: list[tuple[str, str]] = [
        ("prepare_target_database", client.render_ensure_database(request.database))
    ]
    realization: PopulationRealization
    for realization in source_realizations:
        passive_rendered.append(
            (
                f"prepare_source_{_step_segment(realization.resource.name)}",
                _terminate_sql(
                    client.render_resource(
                        resource=realization.resource,
                        database=realization.database,
                        if_not_exists=True,
                    )
                ),
            )
        )
    passive: tuple[WarehouseStatement, ...] = _mutation_statements(
        rendered=tuple(passive_rendered),
        phase=WorkflowPhase.PREPARATION,
        start_sequence=start_sequence,
    )
    bootstrap: tuple[WarehouseStatement, ...] = _mutation_statements(
        rendered=tuple(
            (
                f"bootstrap_source_{_step_segment(landing_view.name)}",
                _render_landing_view_sql(
                    request=request,
                    client=client,
                    landing_view=landing_view,
                ),
            )
            for landing_view in source_preparation.landing_views
        ),
        phase=WorkflowPhase.PREPARATION,
        start_sequence=start_sequence + len(passive),
    )
    bootstrap_wait: tuple[WarehouseStatement, ...] = (
        _wait_statements(
            seconds=request.stabilization_seconds,
            step_id="wait_for_source_bootstrap",
            phase=WorkflowPhase.PREPARATION,
            start_sequence=start_sequence + len(passive) + len(bootstrap),
        )
        if bootstrap and request.stabilization_seconds > 0
        else ()
    )
    paused_landing_view_names: tuple[str, ...] = (
        *preserved_landing_view_names,
        *(landing_view.name for landing_view in source_preparation.landing_views),
    )
    pause: tuple[WarehouseStatement, ...] = _mutation_statements(
        rendered=tuple(
            (
                f"pause_source_{_step_segment(landing_view_name)}",
                f"DROP TABLE IF EXISTS {request.database}.{landing_view_name} SYNC",
            )
            for landing_view_name in paused_landing_view_names
        ),
        phase=WorkflowPhase.PREPARATION,
        start_sequence=start_sequence + len(passive) + len(bootstrap) + len(bootstrap_wait),
    )
    return (*passive, *bootstrap, *bootstrap_wait, *pause)


def _teardown_statements(
    *, request: DirectBuildRequest, start_sequence: int
) -> tuple[WarehouseStatement, ...]:
    rendered: list[tuple[str, str]] = []
    operation: DirectRelationOperation
    for operation in request.plan.teardown_operations:
        relation_type: str = (
            "VIEW" if operation.resource_kind == DirectResourceKind.VIEW else "TABLE"
        )
        rendered.append(
            (
                f"drop_{_step_segment(operation.relation_name)}",
                f"DROP {relation_type} IF EXISTS {request.database}."
                f"{operation.relation_name} SYNC;",
            )
        )
    return _mutation_statements(
        rendered=tuple(rendered),
        phase=WorkflowPhase.TEARDOWN,
        start_sequence=start_sequence,
    )


def _realization_statements(
    *,
    rendered_realizations: tuple[tuple[PopulationRealization, str], ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    rendered: list[tuple[str, str]] = []
    realization: PopulationRealization
    definition_sql: str
    for realization, definition_sql in rendered_realizations:
        rendered.append(
            (
                f"realize_{_step_segment(realization.resource.name)}",
                definition_sql,
            )
        )
    return _mutation_statements(
        rendered=tuple(rendered),
        phase=WorkflowPhase.REALIZATION,
        start_sequence=start_sequence,
    )


def _source_activation_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    source_preparation: PopulationSourcePreparation,
    preserved_landing_views: tuple[DesiredMaterializedView, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    rendered: list[tuple[str, str]] = []
    landing_view: DesiredMaterializedView
    for landing_view in (*preserved_landing_views, *source_preparation.landing_views):
        rendered.append(
            (
                f"activate_source_{_step_segment(landing_view.name)}",
                _render_landing_view_sql(
                    request=request,
                    client=client,
                    landing_view=landing_view,
                ),
            )
        )
    return _mutation_statements(
        rendered=tuple(rendered),
        phase=WorkflowPhase.REPLAY,
        start_sequence=start_sequence,
    )


def _render_landing_view_sql(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    landing_view: DesiredMaterializedView,
) -> str:
    built_resource: object = build_adapter_resource(landing_view)
    if not isinstance(built_resource, AdapterMaterializedView):
        raise DirectBuildError(
            f"Landing view '{landing_view.name}' did not realize as a materialized view"
        )
    return client.render_resource(
        resource=built_resource,
        database=landing_view.key.database or request.database,
        if_not_exists=True,
    )


def _source_recovery_statements(
    *,
    statements: tuple[WarehouseStatement, ...],
    landing_view_names: tuple[str, ...],
) -> tuple[WarehouseStatement, ...]:
    activation_by_step_id: dict[str, WarehouseStatement] = {
        statement.step_id: statement for statement in statements
    }
    return tuple(
        replace(
            activation_by_step_id[f"activate_source_{_step_segment(landing_view_name)}"],
            sequence=index,
            step_id=f"recover_source_{_step_segment(landing_view_name)}",
            phase=WorkflowPhase.FINALIZATION,
        )
        for index, landing_view_name in enumerate(landing_view_names, start=1)
    )


def _stabilization_statements(
    *, seconds: float, start_sequence: int
) -> tuple[WarehouseStatement, ...]:
    return _wait_statements(
        seconds=seconds,
        step_id="wait_for_live_stabilization",
        phase=WorkflowPhase.STABILIZATION,
        start_sequence=start_sequence,
    )


def _wait_statements(
    *,
    seconds: float,
    step_id: str,
    phase: WorkflowPhase,
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    wait_rows: int = max(1, math.ceil(seconds))
    seconds_per_row: float = seconds / wait_rows
    return (
        WarehouseStatement(
            sequence=start_sequence,
            step_id=step_id,
            phase=phase,
            intent=StatementIntent.WAIT,
            sql=(
                f"SELECT sleepEachRow({seconds_per_row:g}) FROM numbers({wait_rows}) "
                "SETTINGS max_block_size = 1;"
            ),
        ),
    )


def _runtime_replay_statements(
    *,
    client: AdapterConnection,
    runtime_replays: tuple[DirectRuntimeReplay, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = []
    runtime_replay: DirectRuntimeReplay
    for runtime_replay in runtime_replays:
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=runtime_replay.capture_step_id,
                phase=WorkflowPhase.REPLAY,
                intent=StatementIntent.QUERY,
                sql=_terminate_sql(
                    client.render_replay_coverage_query(
                        AdapterReplayCoverageRequest(
                            replay=runtime_replay.replay,
                            boundary_column_type=runtime_replay.boundary_column_type,
                        )
                    )
                ),
            )
        )
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=runtime_replay.replay_step_id,
                phase=WorkflowPhase.REPLAY,
                intent=StatementIntent.MUTATION,
                sql=f"/* runtime replay capture: {runtime_replay.model_name} */;",
            )
        )
    return tuple(statements)


def realize_direct_replay_statement(
    *,
    template_statement: WarehouseStatement,
    runtime_replay: DirectRuntimeReplay,
    capture: DirectReplayCapture,
    client: AdapterConnection,
) -> WarehouseStatement:
    """Replace one direct replay template with SQL from its in-memory capture."""

    replay: AdapterReplayRequest = replace(
        runtime_replay.replay,
        boundaries=_captured_boundaries(capture=capture),
    )
    rendered_sql: str = client.render_replay_from_capture(
        AdapterCapturedReplayRequest(
            replay=replay,
            boundary_column_type=runtime_replay.boundary_column_type,
            lower_bounds=_captured_lower_bounds(capture=capture),
        )
    )
    return replace(
        template_statement,
        sql=_terminate_sql(rendered_sql),
        replay_offset_progress=_replay_offset_progress_request(replay=replay, capture=capture),
    )


def _replay_offset_progress_request(
    *, replay: AdapterReplayRequest, capture: DirectReplayCapture
) -> AdapterReplayOffsetProgressRequest | None:
    if capture.boundary_mode != AdapterReplayBoundaryMode.OFFSETS:
        return None
    bounds_by_partition: dict[int, tuple[int, int]] = {}
    for replay_range in capture.ranges:
        partition: int = int(_required_partition(replay_range=replay_range))
        lower_offset: int = int(replay_range.lower_value)
        upper_offset: int = int(replay_range.replay_cutoff_value)
        previous: tuple[int, int] | None = bounds_by_partition.get(partition)
        bounds_by_partition[partition] = (
            lower_offset if previous is None else min(previous[0], lower_offset),
            upper_offset if previous is None else max(previous[1], upper_offset),
        )
    ranges: tuple[AdapterReplayOffsetRange, ...] = tuple(
        AdapterReplayOffsetRange(
            partition=partition,
            lower_offset=bounds_by_partition[partition][0],
            upper_offset=bounds_by_partition[partition][1],
        )
        for partition in sorted(bounds_by_partition)
    )
    if not ranges:
        return None
    return AdapterReplayOffsetProgressRequest(
        database=replay.database,
        relation=replay.relations.target,
        partition_column=replay.columns.partition,
        offset_column=replay.columns.offset,
        ranges=ranges,
    )


def _required_partition(*, replay_range: DirectReplayRange) -> str:
    if replay_range.partition_value is None:
        raise DirectBuildError("Captured offset replay range has no partition")
    return replay_range.partition_value


def _runtime_replays(
    *,
    request: DirectBuildRequest,
    snapshot: DirectWarehouseSnapshot,
    replay_templates: tuple[AdapterReplayRequest, ...],
) -> tuple[DirectRuntimeReplay, ...]:
    runtime_replays: list[DirectRuntimeReplay] = []
    replay: AdapterReplayRequest
    for replay in replay_templates:
        model_name: str = _model_name_for_target(request=request, target=replay.relations.target)
        segment: str = _step_segment(model_name)
        runtime_replays.append(
            DirectRuntimeReplay(
                model_name=model_name,
                capture_step_id=f"capture_replay_{segment}",
                replay_step_id=f"replay_{segment}",
                replay=replay,
                boundary_column_type=_boundary_column_type(
                    request=request,
                    replay=replay,
                    snapshot=snapshot,
                ),
            )
        )
    return tuple(runtime_replays)


def _captured_boundaries(*, capture: DirectReplayCapture) -> tuple[AdapterReplayBoundary, ...]:
    if capture.boundary_mode != AdapterReplayBoundaryMode.OFFSETS:
        return tuple(
            AdapterReplayBoundary(
                boundary_key=f"_replay_{capture.boundary_mode}",
                cutoff_value=replay_range.replay_cutoff_value,
                cutoff_inclusive=replay_range.cutoff_inclusive,
            )
            for replay_range in capture.ranges[:1]
        )
    cutoff_by_partition: dict[str, int] = {}
    for replay_range in capture.ranges:
        if replay_range.partition_value is None:
            raise DirectBuildError("Captured offset replay range has no partition")
        cutoff_value: int = int(replay_range.replay_cutoff_value)
        cutoff_by_partition[replay_range.partition_value] = max(
            cutoff_value,
            cutoff_by_partition.get(replay_range.partition_value, cutoff_value),
        )
    return tuple(
        AdapterReplayBoundary(
            boundary_key=f"_replay_partition={partition_value}",
            cutoff_value=str(cutoff_by_partition[partition_value]),
            cutoff_inclusive=True,
            partition_value=partition_value,
        )
        for partition_value in sorted(cutoff_by_partition, key=_partition_order)
    )


def _captured_lower_bounds(*, capture: DirectReplayCapture) -> tuple[AdapterReplayLowerBound, ...]:
    if not capture.ranges:
        return ()
    if capture.boundary_mode != AdapterReplayBoundaryMode.OFFSETS:
        return (AdapterReplayLowerBound(value=capture.ranges[0].lower_value),)
    lower_by_partition: dict[str, int] = {}
    for replay_range in capture.ranges:
        if replay_range.partition_value is None:
            raise DirectBuildError("Captured offset replay range has no partition")
        lower_value: int = int(replay_range.lower_value)
        lower_by_partition[replay_range.partition_value] = min(
            lower_value,
            lower_by_partition.get(replay_range.partition_value, lower_value),
        )
    return tuple(
        AdapterReplayLowerBound(
            value=str(lower_by_partition[partition_value]),
            partition_value=partition_value,
        )
        for partition_value in sorted(lower_by_partition, key=_partition_order)
    )


def _partition_order(value: str) -> int:
    return int(value)


def _audit_statements(
    *, audits: tuple[DirectBuildAudit, ...], start_sequence: int
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = []
    audit: DirectBuildAudit
    for audit_index, audit in enumerate(audits, start=1):
        step_prefix: str = f"audit_{audit_index}_{_step_segment(audit.name)}"
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"{step_prefix}_count",
                phase=WorkflowPhase.AUDIT,
                intent=StatementIntent.QUERY,
                sql=(
                    "SELECT count() AS failing_row_count FROM (\n"
                    f"{audit.query}\n) AS __streambuild_audit;"
                ),
                continue_on_error=True,
            )
        )
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"{step_prefix}_sample",
                phase=WorkflowPhase.AUDIT,
                intent=StatementIntent.QUERY,
                sql=(
                    "SELECT * FROM (\n"
                    f"{audit.query}\n) AS __streambuild_audit LIMIT {AUDIT_SAMPLE_LIMIT};"
                ),
                continue_on_error=True,
            )
        )
    return tuple(statements)


def _mutation_statements(
    *,
    rendered: tuple[tuple[str, str], ...],
    phase: WorkflowPhase,
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    return tuple(
        WarehouseStatement(
            sequence=start_sequence + index,
            step_id=step_id,
            phase=phase,
            intent=StatementIntent.MUTATION,
            sql=_terminate_sql(sql),
        )
        for index, (step_id, sql) in enumerate(rendered)
    )


def assemble_direct_fingerprint_statements(
    *, rendered: tuple[str, ...]
) -> tuple[WarehouseStatement, ...]:
    """Wrap optional logical fingerprint SQL for the mutation gateway."""

    return tuple(
        WarehouseStatement(
            sequence=index,
            step_id=f"record_direct_fingerprint_{index}",
            phase=WorkflowPhase.FINALIZATION,
            intent=StatementIntent.MUTATION,
            sql=_terminate_sql(sql),
        )
        for index, sql in enumerate(rendered, start=1)
    )


def _assert_bounded_replay_inputs(
    *,
    request: DirectBuildRequest,
    snapshot: DirectWarehouseSnapshot,
    replay_by_model_name: dict[str, AdapterReplayRequest],
) -> None:
    if request.effective_start_time is None:
        return
    model_name: str
    replay: AdapterReplayRequest
    for model_name, replay in replay_by_model_name.items():
        relation: CatalogRelation | None = snapshot.catalog.relation(replay.relations.anchor)
        if relation is None:
            raise DirectBuildError(
                f"Direct --start-time requires existing replay input "
                f"'{replay.relations.anchor}' for model '{model_name}'; run an ordinary direct "
                "build first to create managed sources and retained lineage."
            )
        time_column: str = _forced_time_column(replay=replay)
        if time_column not in {column.name for column in relation.columns}:
            raise DirectBuildError(
                f"Direct --start-time cannot bound model '{model_name}' because replay input "
                f"'{replay.relations.anchor}' does not expose time-lineage column "
                f"'{time_column}'. Project replay timestamp or landed-at lineage through the "
                "intermediate model before selecting this closure."
            )


def _forced_time_column(*, replay: AdapterReplayRequest) -> str:
    return {
        AdapterReplayBoundaryMode.OFFSETS: replay.columns.landed_at or replay.columns.timestamp,
        AdapterReplayBoundaryMode.CURSOR: replay.columns.timestamp,
        AdapterReplayBoundaryMode.TIMESTAMP: replay.columns.timestamp,
        AdapterReplayBoundaryMode.LANDED_AT: replay.columns.landed_at,
    }[replay.mode]


def _boundary_column_type(
    *,
    request: DirectBuildRequest,
    replay: AdapterReplayRequest,
    snapshot: DirectWarehouseSnapshot,
) -> str | None:
    if replay.mode == AdapterReplayBoundaryMode.OFFSETS:
        return None
    position_column: str = {
        AdapterReplayBoundaryMode.CURSOR: replay.columns.cursor,
        AdapterReplayBoundaryMode.TIMESTAMP: replay.columns.timestamp,
        AdapterReplayBoundaryMode.LANDED_AT: replay.columns.landed_at,
    }[replay.mode]
    desired: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    for desired in request.realized_project.desired_state.objects:
        if isinstance(desired, DesiredTable) and desired.name == replay.relations.anchor:
            return next(column.type for column in desired.columns if column.name == position_column)
    relation: CatalogRelation | None = snapshot.catalog.relation(replay.relations.anchor)
    if relation is not None:
        return next(column.type for column in relation.columns if column.name == position_column)
    raise DirectBuildError(
        f"Cannot resolve boundary type for {replay.relations.anchor}.{position_column}"
    )


def _model_name_for_target(*, request: DirectBuildRequest, target: str) -> str:
    return next(
        entry.model_key.name for entry in request.plan.entries if target in entry.relation_names
    )


def _retired_relation_names(*, request: DirectBuildRequest) -> tuple[str, ...]:
    current_names: frozenset[str] = frozenset(_entry_relation_names(request=request))
    return tuple(
        operation.relation_name
        for operation in request.plan.teardown_operations
        if operation.relation_name not in current_names
    )


def _terminate_sql(sql: str) -> str:
    return f"{sql.rstrip().rstrip(';')};"


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _step_segment(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)


def _entry_relation_names(*, request: DirectBuildRequest) -> tuple[str, ...]:
    names: list[str] = []
    entry: DirectPlanEntry
    for entry in request.plan.entries:
        names.extend(entry.relation_names)
    return tuple(names)
