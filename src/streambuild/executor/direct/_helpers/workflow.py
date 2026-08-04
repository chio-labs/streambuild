"""Assemble the complete authoritative direct build workflow."""

from __future__ import annotations

import math

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME,
    METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME,
)
from streambuild.adapter.models import (
    AdapterMaterializedView,
    AdapterOwnershipRecord,
    AdapterOwnershipReplayRequest,
    AdapterReplayCoverageRequest,
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
from streambuild.compiler.planner.main.classify_direct_ownership import (
    classify_direct_ownership,
)
from streambuild.compiler.planner.main.load_direct_warehouse_snapshot import (
    load_direct_warehouse_snapshot,
)
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectPlanEntry,
    DirectRelationOperation,
    DirectWarehouseSnapshot,
    TargetOwnershipClassification,
)
from streambuild.compiler.planner.types import DirectResourceKind
from streambuild.executor.auditing.constants import AUDIT_SAMPLE_LIMIT
from streambuild.executor.direct._helpers.ownership import build_direct_ownership_records
from streambuild.executor.direct._helpers.population_plan import build_direct_population_plan
from streambuild.executor.direct._helpers.preflight import reject_incapable_adapter
from streambuild.executor.direct._helpers.sources import plan_preserved_managed_sources
from streambuild.executor.direct.exceptions import DirectBuildError
from streambuild.executor.direct.models import DirectBuildAudit, DirectBuildRequest
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
    *, request: DirectBuildRequest, client: AdapterConnection, plan_json: str
) -> BuildWorkflow:
    """Resolve preconditions and assemble every direct lifecycle statement once."""

    reject_incapable_adapter(client=client)
    snapshot: DirectWarehouseSnapshot = load_direct_warehouse_snapshot(
        client=client,
        database=request.database,
        metadata_database=request.metadata_database,
    )
    _assert_confirmed_ownership(plan=request.plan, snapshot=snapshot)
    source_preparation: PopulationSourcePreparation
    source_realizations: tuple[PopulationRealization, ...]
    source_preparation, source_realizations = plan_preserved_managed_sources(
        realized_project=request.realized_project,
        catalog=snapshot.catalog,
        database=request.database,
    )
    population_plan: PopulationPlan = expand_population_plan(
        plan=build_direct_population_plan(
            plan=request.plan,
            realized_project=request.realized_project,
        ),
        desired_state=request.realized_project.desired_state,
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
    ownership_records: tuple[AdapterOwnershipRecord, ...] = build_direct_ownership_records(
        plan=request.plan,
        database=request.database,
        tool_version=request.tool_version,
    )
    statements: tuple[WarehouseStatement, ...] = _assemble_statements(
        request=request,
        client=client,
        snapshot=snapshot,
        source_preparation=source_preparation,
        source_realizations=source_realizations,
        ownership_records=ownership_records,
        population_plan=population_plan,
        replay_templates=replay_templates,
    )
    return BuildWorkflow(mode=WorkflowMode.DIRECT, plan_json=plan_json, statements=statements)


def _assemble_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    snapshot: DirectWarehouseSnapshot,
    source_preparation: PopulationSourcePreparation,
    source_realizations: tuple[PopulationRealization, ...],
    ownership_records: tuple[AdapterOwnershipRecord, ...],
    population_plan: PopulationPlan,
    replay_templates: tuple[AdapterReplayRequest, ...],
) -> tuple[WarehouseStatement, ...]:
    preparation: tuple[WarehouseStatement, ...] = _preparation_statements(
        request=request,
        client=client,
        source_realizations=source_realizations,
        start_sequence=1,
    )
    ownership: tuple[WarehouseStatement, ...] = _initial_ownership_statements(
        request=request,
        client=client,
        records=ownership_records,
        start_sequence=len(preparation) + 1,
    )
    teardown: tuple[WarehouseStatement, ...] = _teardown_statements(
        request=request,
        start_sequence=len(preparation) + len(ownership) + 1,
    )
    realization: tuple[WarehouseStatement, ...] = _realization_statements(
        request=request,
        client=client,
        population_plan=population_plan,
        source_preparation=source_preparation,
        start_sequence=len(preparation) + len(ownership) + len(teardown) + 1,
    )
    stabilization: tuple[WarehouseStatement, ...] = _stabilization_statements(
        seconds=request.stabilization_seconds,
        start_sequence=(len(preparation) + len(ownership) + len(teardown) + len(realization) + 1),
    )
    prior_count: int = sum(
        len(phase) for phase in (preparation, ownership, teardown, realization, stabilization)
    )
    boundary: tuple[WarehouseStatement, ...] = _boundary_statements(
        request=request,
        client=client,
        snapshot=snapshot,
        replay_templates=replay_templates,
        start_sequence=prior_count + 1,
    )
    replay: tuple[WarehouseStatement, ...] = _replay_statements(
        request=request,
        client=client,
        snapshot=snapshot,
        replay_templates=replay_templates,
        start_sequence=prior_count + len(boundary) + 1,
    )
    audit: tuple[WarehouseStatement, ...] = _audit_statements(
        audits=request.audits,
        start_sequence=prior_count + len(boundary) + len(replay) + 1,
    )
    finalization: tuple[WarehouseStatement, ...] = _finalization_statements(
        request=request,
        client=client,
        start_sequence=prior_count + len(boundary) + len(replay) + len(audit) + 1,
    )
    return (
        *preparation,
        *ownership,
        *teardown,
        *realization,
        *stabilization,
        *boundary,
        *replay,
        *audit,
        *finalization,
    )


def _preparation_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    source_realizations: tuple[PopulationRealization, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    rendered: list[tuple[str, str]] = [
        ("prepare_target_database", client.render_ensure_database(request.database))
    ]
    rendered.extend(
        (f"prepare_metadata_{index}", sql)
        for index, sql in enumerate(
            client.render_migrate_metadata_state(request.metadata_database), start=1
        )
    )
    realization: PopulationRealization
    for realization in source_realizations:
        rendered.append(
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
    return _mutation_statements(
        rendered=tuple(rendered),
        phase=WorkflowPhase.PREPARATION,
        start_sequence=start_sequence,
    )


def _initial_ownership_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    records: tuple[AdapterOwnershipRecord, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    rendered: tuple[tuple[str, str], ...] = tuple(
        (f"claim_ownership_{index}", sql)
        for index, sql in enumerate(
            client.render_record_target_ownership(
                database=request.metadata_database,
                records=records,
            ),
            start=1,
        )
    )
    return _mutation_statements(
        rendered=rendered,
        phase=WorkflowPhase.OWNERSHIP,
        start_sequence=start_sequence,
    )


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
    request: DirectBuildRequest,
    client: AdapterConnection,
    population_plan: PopulationPlan,
    source_preparation: PopulationSourcePreparation,
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    realizations: tuple[PopulationRealization, ...] = plan_population_objects(
        plan=population_plan,
        desired_state=request.realized_project.desired_state,
        default_database=request.database,
    )
    rendered: list[tuple[str, str]] = []
    realization: PopulationRealization
    for realization in realizations:
        rendered.append(
            (
                f"realize_{_step_segment(realization.resource.name)}",
                _terminate_sql(
                    client.render_resource(
                        resource=realization.resource,
                        database=realization.database,
                    )
                ),
            )
        )
    landing_view: DesiredMaterializedView
    for landing_view in source_preparation.landing_views:
        built_resource: object = build_adapter_resource(landing_view)
        if not isinstance(built_resource, AdapterMaterializedView):
            raise DirectBuildError(
                f"Landing view '{landing_view.name}' did not realize as a materialized view"
            )
        resource: AdapterMaterializedView = built_resource
        rendered.append(
            (
                f"activate_source_{_step_segment(resource.name)}",
                _terminate_sql(
                    client.render_resource(
                        resource=resource,
                        database=landing_view.key.database or request.database,
                        if_not_exists=True,
                    )
                ),
            )
        )
    return _mutation_statements(
        rendered=tuple(rendered),
        phase=WorkflowPhase.REALIZATION,
        start_sequence=start_sequence,
    )


def _stabilization_statements(
    *, seconds: float, start_sequence: int
) -> tuple[WarehouseStatement, ...]:
    wait_rows: int = max(1, math.ceil(seconds))
    seconds_per_row: float = seconds / wait_rows
    return (
        WarehouseStatement(
            sequence=start_sequence,
            step_id="wait_for_live_stabilization",
            phase=WorkflowPhase.STABILIZATION,
            intent=StatementIntent.WAIT,
            sql=(
                f"SELECT sleepEachRow({seconds_per_row:g}) FROM numbers({wait_rows}) "
                "SETTINGS max_block_size = 1;"
            ),
        ),
    )


def _boundary_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    snapshot: DirectWarehouseSnapshot,
    replay_templates: tuple[AdapterReplayRequest, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = []
    replay: AdapterReplayRequest
    for replay in replay_templates:
        model_name: str = _model_name_for_target(request=request, target=replay.relations.target)
        statements.extend(
            _capture_coverage_statements(
                request=request,
                client=client,
                snapshot=snapshot,
                replay=replay,
                model_name=model_name,
                step_prefix="capture_boundary",
                phase=WorkflowPhase.BOUNDARY,
                start_sequence=start_sequence + len(statements),
            )
        )
    return tuple(statements)


def _replay_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    snapshot: DirectWarehouseSnapshot,
    replay_templates: tuple[AdapterReplayRequest, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = []
    replay: AdapterReplayRequest
    for replay in replay_templates:
        model_name: str = _model_name_for_target(request=request, target=replay.relations.target)
        boundary_column_type: str | None = _boundary_column_type(
            request=request,
            replay=replay,
            snapshot=snapshot,
        )
        statements.extend(
            _capture_coverage_statements(
                request=request,
                client=client,
                snapshot=snapshot,
                replay=replay,
                model_name=model_name,
                step_prefix="refresh_boundary",
                phase=WorkflowPhase.REPLAY,
                start_sequence=start_sequence + len(statements),
            )
        )
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"read_boundary_{_step_segment(model_name)}",
                phase=WorkflowPhase.REPLAY,
                intent=StatementIntent.QUERY,
                sql=_read_boundary_sql(request=request, replay=replay, model_name=model_name),
            )
        )
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"replay_{_step_segment(model_name)}",
                phase=WorkflowPhase.REPLAY,
                intent=StatementIntent.MUTATION,
                sql=_terminate_sql(
                    client.render_replay_from_ownership(
                        AdapterOwnershipReplayRequest(
                            replay=replay,
                            metadata_database=request.metadata_database,
                            logical_model_name=model_name,
                            boundary_column_type=boundary_column_type,
                        )
                    )
                ),
            )
        )
        statements.extend(
            _capture_coverage_statements(
                request=request,
                client=client,
                snapshot=snapshot,
                replay=replay,
                model_name=model_name,
                step_prefix="refresh_coverage",
                phase=WorkflowPhase.REPLAY,
                start_sequence=start_sequence + len(statements),
            )
        )
    return tuple(statements)


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


def _finalization_statements(
    *, request: DirectBuildRequest, client: AdapterConnection, start_sequence: int
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = [
        WarehouseStatement(
            sequence=start_sequence,
            step_id="read_final_ownership",
            phase=WorkflowPhase.FINALIZATION,
            intent=StatementIntent.QUERY,
            sql=_read_final_ownership_sql(request=request),
        )
    ]
    retired_names: tuple[str, ...] = _retired_relation_names(request=request)
    removal_sql: str
    for removal_sql in client.render_remove_target_ownership(
        database=request.metadata_database,
        target_database=request.database,
        relation_names=retired_names,
    ):
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id="remove_retired_ownership",
                phase=WorkflowPhase.FINALIZATION,
                intent=StatementIntent.MUTATION,
                sql=removal_sql,
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


def _assert_confirmed_ownership(*, plan: DirectPlan, snapshot: DirectWarehouseSnapshot) -> None:
    expected: tuple[TargetOwnershipClassification, ...] = _ownership_classifications(plan=plan)
    current: tuple[TargetOwnershipClassification, ...] = classify_direct_ownership(
        snapshot=snapshot,
        relation_names=tuple(classification.relation_name for classification in expected),
    )
    changed: tuple[str, ...] = tuple(
        f"{expected_value.relation_name}: expected {expected_value.ownership}, "
        f"current {current_value.ownership}"
        for expected_value, current_value in zip(expected, current, strict=True)
        if expected_value.ownership != current_value.ownership
    )
    if changed:
        raise DirectBuildError(
            "Direct ownership changed after confirmation: "
            f"{'; '.join(changed)}. Rerun stb plan or stb build."
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


def _capture_coverage_statements(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    snapshot: DirectWarehouseSnapshot,
    replay: AdapterReplayRequest,
    model_name: str,
    step_prefix: str,
    phase: WorkflowPhase,
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    segment: str = _step_segment(model_name)
    return (
        WarehouseStatement(
            sequence=start_sequence,
            step_id=f"{step_prefix}_{segment}_ranges",
            phase=phase,
            intent=StatementIntent.MUTATION,
            sql=_capture_replay_set_sql(
                request=request,
                client=client,
                snapshot=snapshot,
                replay=replay,
                model_name=model_name,
            ),
        ),
        WarehouseStatement(
            sequence=start_sequence + 1,
            step_id=f"{step_prefix}_{segment}_targets",
            phase=phase,
            intent=StatementIntent.MUTATION,
            sql=_refresh_target_events_sql(request=request, model_name=model_name),
        ),
    )


def _capture_replay_set_sql(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    snapshot: DirectWarehouseSnapshot,
    replay: AdapterReplayRequest,
    model_name: str,
) -> str:
    coverage_query: str = client.render_replay_coverage_query(
        _coverage_request(request=request, replay=replay, snapshot=snapshot)
    )
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        "(replay_set_id, target_database_name, logical_model_database, logical_model_name, "
        "range_present, "
        "driving_input_relation_name, replay_boundary_mode, partition_value, "
        "source_partition_column_name, source_position_column_name, "
        "source_timestamp_column_name, lower_value, upper_value, replay_cutoff_value, "
        "captured_at)\n"
        f"WITH coverage_payload AS (\n{coverage_query}\n),\n"
        "captured AS (SELECT value, lower(hex(SHA256(concat("
        f"'{_escape_literal(request.database)}', ':', '{_escape_literal(model_name)}', ':', "
        "value)))) AS replay_set_id, now64(3, 'UTC') AS captured_at FROM coverage_payload)\n"
        f"SELECT replay_set_id, '{_escape_literal(request.database)}', NULL, "
        f"'{_escape_literal(model_name)}', coverage != '', "
        "nullIf(JSONExtractString(coverage, 'driving_input_relation_name'), ''), "
        "nullIf(JSONExtractString(coverage, 'replay_boundary_mode'), ''), "
        "if(startsWith(JSONExtractString(coverage, 'boundary_key'), '_replay_partition='), "
        "splitByChar('=', JSONExtractString(coverage, 'boundary_key'))[2], NULL), "
        "nullIf(JSONExtractString(coverage, 'source_partition_column_name'), ''), "
        "nullIf(JSONExtractString(coverage, 'source_position_column_name'), ''), "
        "nullIf(JSONExtractString(coverage, 'source_timestamp_column_name'), ''), "
        "nullIf(JSONExtractString(coverage, 'lower_value'), ''), "
        "nullIf(JSONExtractString(coverage, 'upper_value'), ''), "
        "coalesce(nullIf(JSONExtractString(coverage, 'replay_cutoff_value'), ''), "
        "nullIf(JSONExtractString(coverage, 'upper_value'), '')), captured_at\n"
        "FROM captured ARRAY JOIN if(value = '[]', [''], JSONExtractArrayRaw(value)) AS coverage;"
    )


def _refresh_target_events_sql(*, request: DirectBuildRequest, model_name: str) -> str:
    entry: DirectPlanEntry = next(
        entry for entry in request.plan.entries if entry.model_key.name == model_name
    )
    relations: str = ", ".join(
        f"('{_escape_literal(name)}', '{_escape_literal(str(kind))}')"
        for name, kind in zip(entry.relation_names, entry.resource_kinds, strict=True)
    )
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} "
        "(event_id, workflow_id, event_kind, database_name, relation_name, resource_kind, "
        "logical_model_database, logical_model_name, tool_version, replay_set_id, recorded_at)\n"
        "WITH latest_set AS (SELECT argMax(tuple(replay_set_id, captured_at), "
        "tuple(captured_at, replay_set_id)) AS current_set FROM "
        f"{request.metadata_database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        f"WHERE target_database_name = '{_escape_literal(request.database)}' "
        f"AND logical_model_name = '{_escape_literal(model_name)}')\n"
        "SELECT lower(hex(SHA256(concat(current_set.1, ':', tupleElement(relation, 1), "
        "':refreshed')))), current_set.1, 'refreshed', "
        f"'{_escape_literal(request.database)}', tupleElement(relation, 1), "
        "tupleElement(relation, 2), NULL, "
        f"'{_escape_literal(model_name)}', '{_escape_literal(request.tool_version)}', "
        "current_set.1, current_set.2 FROM latest_set\n"
        f"ARRAY JOIN [{relations}] AS relation;"
    )


def _coverage_request(
    *,
    request: DirectBuildRequest,
    replay: AdapterReplayRequest,
    snapshot: DirectWarehouseSnapshot,
) -> AdapterReplayCoverageRequest:
    return AdapterReplayCoverageRequest(
        replay=replay,
        boundary_column_type=_boundary_column_type(
            request=request,
            replay=replay,
            snapshot=snapshot,
        ),
    )


def _read_boundary_sql(
    *, request: DirectBuildRequest, replay: AdapterReplayRequest, model_name: str
) -> str:
    boundary_key: str = (
        "concat('_replay_partition=', partition_value)"
        if replay.mode == AdapterReplayBoundaryMode.OFFSETS
        else f"'{_direct_boundary_key(replay.mode)}'"
    )
    return (
        "WITH current_target AS (SELECT argMax(tuple(replay_set_id, recorded_at), "
        "tuple(recorded_at, event_id)) AS current_set FROM "
        f"{request.metadata_database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} "
        f"WHERE database_name = '{_escape_literal(request.database)}' AND relation_name = "
        f"'{_escape_literal(replay.relations.target)}')\n"
        f"SELECT DISTINCT '{_escape_literal(model_name)}' AS model_name, "
        f"driving_input_relation_name, replay_boundary_mode, {boundary_key} AS boundary_key, "
        "replay_cutoff_value AS cutoff_value FROM "
        f"{request.metadata_database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        "INNER JOIN current_target ON replay_set_id = current_target.current_set.1 "
        f"WHERE target_database_name = '{_escape_literal(request.database)}' AND range_present "
        "ORDER BY boundary_key;"
    )


def _direct_boundary_key(mode: AdapterReplayBoundaryMode) -> str:
    return {
        AdapterReplayBoundaryMode.TIMESTAMP: "_replay_timestamp",
        AdapterReplayBoundaryMode.LANDED_AT: "_replay_landed_at",
        AdapterReplayBoundaryMode.CURSOR: "_replay_cursor",
    }[mode]


def _read_final_ownership_sql(*, request: DirectBuildRequest) -> str:
    relation_names: tuple[str, ...] = _entry_relation_names(request=request)
    quoted_names: str = ", ".join(
        f"'{_escape_literal(relation_name)}'" for relation_name in relation_names
    )
    return (
        "WITH current_events AS (SELECT database_name, relation_name, "
        "argMax(tuple(event_kind, resource_kind, logical_model_database, logical_model_name, "
        "tool_version, replay_set_id), tuple(recorded_at, event_id)) AS current_state FROM "
        f"{request.metadata_database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} "
        f"WHERE database_name = '{_escape_literal(request.database)}' AND relation_name IN "
        f"({quoted_names}) GROUP BY database_name, relation_name),\n"
        "coverage AS (SELECT replay_set_id, concat('[', arrayStringConcat(groupUniqArrayIf("
        "toJSONString(map('driving_input_relation_name', driving_input_relation_name, "
        "'replay_boundary_mode', replay_boundary_mode, 'boundary_key', "
        "if(replay_boundary_mode = 'offsets', concat('_replay_partition=', partition_value), "
        "concat('_replay_', replay_boundary_mode)), 'source_partition_column_name', "
        "coalesce(source_partition_column_name, ''), 'source_position_column_name', "
        "source_position_column_name, 'source_timestamp_column_name', "
        "coalesce(source_timestamp_column_name, ''), 'lower_value', lower_value, "
        "'upper_value', upper_value)), range_present), ','), ']') AS replay_coverage_json "
        f"FROM {request.metadata_database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        f"WHERE target_database_name = '{_escape_literal(request.database)}' "
        "GROUP BY replay_set_id) SELECT database_name, relation_name, current_state.2, "
        "current_state.3, current_state.4, 'direct', current_state.5, "
        "coalesce(nullIf(coverage.replay_coverage_json, ''), '[]') FROM current_events "
        "LEFT JOIN coverage "
        "ON coverage.replay_set_id = current_state.6 WHERE current_state.1 != 'released' "
        "ORDER BY relation_name;"
    )


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


def _ownership_classifications(*, plan: DirectPlan) -> tuple[TargetOwnershipClassification, ...]:
    classifications: list[TargetOwnershipClassification] = []
    entry: DirectPlanEntry
    for entry in plan.entries:
        classifications.extend(entry.ownership)
    return tuple(classifications)


def _entry_relation_names(*, request: DirectBuildRequest) -> tuple[str, ...]:
    names: list[str] = []
    entry: DirectPlanEntry
    for entry in request.plan.entries:
        names.extend(entry.relation_names)
    return tuple(names)
