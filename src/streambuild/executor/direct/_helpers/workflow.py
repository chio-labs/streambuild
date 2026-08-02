"""Assemble the complete authoritative direct build workflow."""

from __future__ import annotations

import math

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import METADATA_TARGET_OWNERSHIP_TABLE_NAME
from streambuild.adapter.models import (
    AdapterMaterializedView,
    AdapterOwnershipRecord,
    AdapterOwnershipReplayRequest,
    AdapterReplayCoverageRange,
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
from streambuild.compiler.planner.types import DirectResourceKind, TargetOwnership
from streambuild.executor.auditing.types import AuditSeverity
from streambuild.executor.direct._helpers.ownership import build_direct_ownership_records
from streambuild.executor.direct._helpers.population_plan import build_direct_population_plan
from streambuild.executor.direct._helpers.preflight import reject_incapable_adapter
from streambuild.executor.direct._helpers.relations import target_relation_name_by_model_name
from streambuild.executor.direct._helpers.retention import resolve_required_replay_coverage
from streambuild.executor.direct._helpers.sources import plan_preserved_managed_sources
from streambuild.executor.direct.exceptions import DirectBuildError
from streambuild.executor.direct.models import (
    DirectBuildAudit,
    DirectBuildRequest,
    DirectReplayCoverage,
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
    replay_coverage: tuple[DirectReplayCoverage, ...] = resolve_required_replay_coverage(
        client=client,
        plan=request.plan,
        database=request.database,
        existing_relation_names=snapshot.catalog.relation_names(),
        existing_ownership=snapshot.ownership_records,
        target_relation_name_by_model_name=target_relation_name_by_model_name(plan=request.plan),
    )
    ownership_records: tuple[AdapterOwnershipRecord, ...] = build_direct_ownership_records(
        plan=request.plan,
        database=request.database,
        tool_version=request.tool_version,
        replay_coverage=replay_coverage,
    )
    population_plan: PopulationPlan = expand_population_plan(
        plan=build_direct_population_plan(
            plan=request.plan,
            realized_project=request.realized_project,
        ),
        desired_state=request.realized_project.desired_state,
    )
    replay_templates: tuple[tuple[ObjectKey, AdapterReplayRequest], ...] = (
        build_population_replay_templates(
            plan=population_plan,
            desired_state=request.realized_project.desired_state,
            default_database=request.database,
        )
    )
    statements: tuple[WarehouseStatement, ...] = _assemble_statements(
        request=request,
        client=client,
        snapshot=snapshot,
        source_preparation=source_preparation,
        source_realizations=source_realizations,
        ownership_records=ownership_records,
        replay_coverage=replay_coverage,
        population_plan=population_plan,
        replay_templates=tuple(template for _key, template in replay_templates),
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
    replay_coverage: tuple[DirectReplayCoverage, ...],
    population_plan: PopulationPlan,
    replay_templates: tuple[AdapterReplayRequest, ...],
) -> tuple[WarehouseStatement, ...]:
    preflight: tuple[WarehouseStatement, ...] = _preflight_statements(
        request=request,
        snapshot=snapshot,
        source_preparation=source_preparation,
        replay_coverage=replay_coverage,
    )
    preparation: tuple[WarehouseStatement, ...] = _preparation_statements(
        request=request,
        client=client,
        source_realizations=source_realizations,
        start_sequence=len(preflight) + 1,
    )
    ownership: tuple[WarehouseStatement, ...] = _initial_ownership_statements(
        request=request,
        client=client,
        records=ownership_records,
        start_sequence=len(preflight) + len(preparation) + 1,
    )
    teardown: tuple[WarehouseStatement, ...] = _teardown_statements(
        request=request,
        start_sequence=len(preflight) + len(preparation) + len(ownership) + 1,
    )
    realization: tuple[WarehouseStatement, ...] = _realization_statements(
        request=request,
        client=client,
        population_plan=population_plan,
        source_preparation=source_preparation,
        start_sequence=len(preflight) + len(preparation) + len(ownership) + len(teardown) + 1,
    )
    stabilization: tuple[WarehouseStatement, ...] = _stabilization_statements(
        seconds=request.stabilization_seconds,
        start_sequence=(
            len(preflight)
            + len(preparation)
            + len(ownership)
            + len(teardown)
            + len(realization)
            + 1
        ),
    )
    prior_count: int = sum(
        len(phase)
        for phase in (preflight, preparation, ownership, teardown, realization, stabilization)
    )
    boundary: tuple[WarehouseStatement, ...] = _boundary_statements(
        request=request,
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
        *preflight,
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


def _preflight_statements(
    *,
    request: DirectBuildRequest,
    snapshot: DirectWarehouseSnapshot,
    source_preparation: PopulationSourcePreparation,
    replay_coverage: tuple[DirectReplayCoverage, ...],
) -> tuple[WarehouseStatement, ...]:
    sql_statements: list[tuple[str, str]] = []
    entry: DirectPlanEntry
    for entry in request.plan.entries:
        classification: TargetOwnershipClassification
        for classification in entry.ownership:
            sql_statements.append(
                (
                    f"assert_ownership_{_step_segment(classification.relation_name)}",
                    _ownership_assertion_sql(
                        classification=classification,
                        target_database=request.database,
                        metadata_database=request.metadata_database,
                    ),
                )
            )
    source_name: str
    for source_name in source_preparation.preserved_relation_names:
        relation: CatalogRelation = _required_relation(snapshot=snapshot, relation_name=source_name)
        sql_statements.append(
            (
                f"assert_source_{_step_segment(source_name)}",
                _source_assertion_sql(
                    database=request.database,
                    relation_name=source_name,
                    definition_sql=relation.definition_sql or "",
                ),
            )
        )
    coverage: DirectReplayCoverage
    replay_range: AdapterReplayCoverageRange
    for coverage in replay_coverage:
        for replay_range in coverage.ranges:
            sql_statements.append(
                (
                    f"assert_retention_{_step_segment(coverage.model_name)}_"
                    f"{len(sql_statements) + 1}",
                    _retention_assertion_sql(database=request.database, replay_range=replay_range),
                )
            )
    return tuple(
        WarehouseStatement(
            sequence=index,
            step_id=step_id,
            phase=WorkflowPhase.PREFLIGHT,
            intent=StatementIntent.ASSERTION,
            sql=sql,
        )
        for index, (step_id, sql) in enumerate(sql_statements, start=1)
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
    replay_templates: tuple[AdapterReplayRequest, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = []
    replay: AdapterReplayRequest
    for replay in replay_templates:
        model_name: str = _model_name_for_target(request=request, target=replay.relations.target)
        sequence: int = start_sequence + len(statements)
        statements.append(
            WarehouseStatement(
                sequence=sequence,
                step_id=f"capture_boundary_{_step_segment(model_name)}",
                phase=WorkflowPhase.BOUNDARY,
                intent=StatementIntent.MUTATION,
                sql=_capture_coverage_sql(request=request, replay=replay, model_name=model_name),
            )
        )
        statements.append(
            WarehouseStatement(
                sequence=sequence + 1,
                step_id=f"read_boundary_{_step_segment(model_name)}",
                phase=WorkflowPhase.BOUNDARY,
                intent=StatementIntent.QUERY,
                sql=_read_boundary_sql(request=request, replay=replay, model_name=model_name),
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
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"refresh_boundary_{_step_segment(model_name)}",
                phase=WorkflowPhase.REPLAY,
                intent=StatementIntent.MUTATION,
                sql=_capture_coverage_sql(request=request, replay=replay, model_name=model_name),
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
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"refresh_coverage_{_step_segment(model_name)}",
                phase=WorkflowPhase.REPLAY,
                intent=StatementIntent.MUTATION,
                sql=_capture_coverage_sql(request=request, replay=replay, model_name=model_name),
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
            )
        )
        if audit.severity == AuditSeverity.ERROR:
            statements.append(
                WarehouseStatement(
                    sequence=start_sequence + len(statements),
                    step_id=f"{step_prefix}_error",
                    phase=WorkflowPhase.AUDIT,
                    intent=StatementIntent.ASSERTION,
                    sql=(
                        "SELECT throwIf(count() > 0, "
                        f"'Direct audit {_escape_literal(audit.name)} failed') FROM (\n"
                        f"{audit.query}\n) AS __streambuild_audit;"
                    ),
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


def _ownership_assertion_sql(
    *,
    classification: TargetOwnershipClassification,
    target_database: str,
    metadata_database: str,
) -> str:
    relation_name: str = _escape_literal(classification.relation_name)
    message: str = _escape_literal(
        f"Direct ownership changed for {classification.relation_name}; rerun stb plan or stb build"
    )
    if classification.ownership == TargetOwnership.ABSENT:
        return (
            "SELECT throwIf(count() > 0, "
            f"'{message}') FROM system.tables WHERE database = "
            f"'{_escape_literal(target_database)}' AND "
            f"(name = '{relation_name}' OR startsWith(name, '{relation_name}__'));"
        )
    return (
        "SELECT throwIf(count() != 1 OR any(owning_mode) != 'direct', "
        f"'{message}') FROM {metadata_database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} FINAL "
        f"WHERE database_name = '{_escape_literal(target_database)}' "
        f"AND relation_name = '{relation_name}';"
    )


def _source_assertion_sql(*, database: str, relation_name: str, definition_sql: str) -> str:
    message: str = _escape_literal(f"Preserved source {relation_name} changed after confirmation")
    return (
        "SELECT throwIf(count() != 1 OR any(create_table_query) != "
        f"'{_escape_literal(definition_sql)}', '{message}') FROM system.tables "
        f"WHERE database = '{_escape_literal(database)}' "
        f"AND name = '{_escape_literal(relation_name)}';"
    )


def _retention_assertion_sql(*, database: str, replay_range: AdapterReplayCoverageRange) -> str:
    source: str = replay_range.driving_input_relation_name
    message: str = _escape_literal(
        "Direct rerun would silently drop retained history because the preserved driving input "
        "no longer covers the required replay range: "
        f"{source} requires {replay_range.boundary_key} "
        f"{replay_range.lower_value}..{replay_range.upper_value}"
    )
    if replay_range.replay_boundary_mode == AdapterReplayBoundaryMode.OFFSETS:
        partition: str = replay_range.boundary_key.split("=", 1)[1]
        expected_count: int = int(replay_range.upper_value) - int(replay_range.lower_value) + 1
        return (
            f"SELECT throwIf(countDistinct({replay_range.source_position_column_name}) != "
            f"{expected_count}, '{message}') FROM {database}.{source} "
            f"WHERE toString({replay_range.source_partition_column_name}) = "
            f"'{_escape_literal(partition)}' AND {replay_range.source_position_column_name} "
            f"BETWEEN {replay_range.lower_value} AND {replay_range.upper_value};"
        )
    return (
        "SELECT throwIf(count() = 0 OR "
        f"min({replay_range.source_position_column_name}) > "
        f"{_typed_replay_value(replay_range=replay_range, value=replay_range.lower_value)} OR "
        f"max({replay_range.source_position_column_name}) < "
        f"{_typed_replay_value(replay_range=replay_range, value=replay_range.upper_value)}, "
        f"'{message}') "
        f"FROM {database}.{source};"
    )


def _capture_coverage_sql(
    *, request: DirectBuildRequest, replay: AdapterReplayRequest, model_name: str
) -> str:
    entry: DirectPlanEntry = next(
        entry for entry in request.plan.entries if entry.model_key.name == model_name
    )
    coverage_query: str = (
        _offset_coverage_query(replay=replay)
        if replay.mode == AdapterReplayBoundaryMode.OFFSETS
        else _scalar_coverage_query(replay=replay)
    )
    relations: str = ", ".join(
        f"('{_escape_literal(name)}', '{_escape_literal(str(kind))}')"
        for name, kind in zip(entry.relation_names, entry.resource_kinds, strict=True)
    )
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} "
        "(database_name, relation_name, resource_kind, logical_model_database, "
        "logical_model_name, owning_mode, tool_version, replay_coverage_json, created_at, "
        "updated_at)\n"
        f"WITH coverage_payload AS (\n{coverage_query}\n),\n"
        "next_timestamp AS (SELECT greatest(now64(3, 'UTC'), "
        f"coalesce(max(updated_at) + toIntervalMillisecond(1), now64(3, 'UTC'))) AS value "
        f"FROM {request.metadata_database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} "
        f"WHERE database_name = '{_escape_literal(request.database)}' "
        f"AND logical_model_name = '{_escape_literal(model_name)}')\n"
        f"SELECT '{_escape_literal(request.database)}', tupleElement(relation, 1), "
        "tupleElement(relation, 2), NULL, "
        f"'{_escape_literal(model_name)}', 'direct', "
        f"'{_escape_literal(request.tool_version)}', coverage_payload.value, "
        "next_timestamp.value, next_timestamp.value\n"
        "FROM coverage_payload CROSS JOIN next_timestamp\n"
        f"ARRAY JOIN [{relations}] AS relation;"
    )


def _offset_coverage_query(*, replay: AdapterReplayRequest) -> str:
    timestamp_column: str = replay.columns.timestamp or ""
    return (
        "SELECT toJSONString(groupArray(map("
        f"'driving_input_relation_name', '{_escape_literal(replay.relations.anchor)}', "
        "'replay_boundary_mode', 'offsets', "
        f"'boundary_key', concat('_replay_partition=', toString(partition_value)), "
        f"'source_partition_column_name', '{_escape_literal(replay.columns.partition)}', "
        f"'source_position_column_name', '{_escape_literal(replay.columns.offset)}', "
        f"'source_timestamp_column_name', '{_escape_literal(timestamp_column)}', "
        "'lower_value', toString(lower_value), 'upper_value', toString(upper_value)))) AS value\n"
        "FROM (\n"
        f"SELECT partition_value, min(offset_value) AS lower_value, "
        "max(offset_value) AS upper_value\nFROM (\n"
        f"SELECT {replay.columns.partition} AS partition_value, "
        f"{replay.columns.offset} AS offset_value, {replay.columns.offset} - "
        f"toInt64(row_number() OVER (PARTITION BY {replay.columns.partition} "
        f"ORDER BY {replay.columns.offset})) AS sequence_group\n"
        f"FROM (SELECT DISTINCT {replay.columns.partition}, {replay.columns.offset} "
        f"FROM {replay.database}.{replay.relations.anchor})\n)\n"
        "GROUP BY partition_value, sequence_group\nORDER BY partition_value, lower_value\n)"
    )


def _scalar_coverage_query(*, replay: AdapterReplayRequest) -> str:
    position_column: str = {
        AdapterReplayBoundaryMode.CURSOR: replay.columns.cursor,
        AdapterReplayBoundaryMode.TIMESTAMP: replay.columns.timestamp,
        AdapterReplayBoundaryMode.LANDED_AT: replay.columns.landed_at,
    }[replay.mode]
    canonical_key: str = {
        AdapterReplayBoundaryMode.CURSOR: "_replay_cursor",
        AdapterReplayBoundaryMode.TIMESTAMP: "_replay_timestamp",
        AdapterReplayBoundaryMode.LANDED_AT: "_replay_landed_at",
    }[replay.mode]
    cutoff_expression: str = (
        f"max({position_column})"
        if replay.mode == AdapterReplayBoundaryMode.CURSOR
        else "now64(3, 'UTC')"
    )
    return (
        "SELECT toJSONString(groupArray(map("
        f"'driving_input_relation_name', '{_escape_literal(replay.relations.anchor)}', "
        f"'replay_boundary_mode', '{replay.mode}', 'boundary_key', '{canonical_key}', "
        "'source_partition_column_name', '', "
        f"'source_position_column_name', '{_escape_literal(position_column)}', "
        f"'source_timestamp_column_name', '{_escape_literal(replay.columns.timestamp)}', "
        "'lower_value', toString(lower_value), 'upper_value', toString(upper_value), "
        "'replay_cutoff_value', toString(cutoff_value)))) AS value\n"
        f"FROM (SELECT min({position_column}) AS lower_value, "
        f"max({position_column}) AS upper_value, {cutoff_expression} AS cutoff_value "
        f"FROM {replay.database}.{replay.relations.anchor} HAVING count() > 0)"
    )


def _read_boundary_sql(
    *, request: DirectBuildRequest, replay: AdapterReplayRequest, model_name: str
) -> str:
    return (
        "WITH latest_coverage AS (SELECT argMax(replay_coverage_json, updated_at) AS value, "
        "max(updated_at) AS boundary_time "
        f"FROM {request.metadata_database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} "
        f"WHERE database_name = '{_escape_literal(request.database)}' "
        f"AND relation_name = '{_escape_literal(replay.relations.target)}' "
        f"AND logical_model_name = '{_escape_literal(model_name)}')\n"
        f"SELECT '{_escape_literal(model_name)}' AS model_name, "
        "JSONExtractString(coverage, 'driving_input_relation_name') "
        "AS driving_input_relation_name, "
        "JSONExtractString(coverage, 'replay_boundary_mode') AS replay_boundary_mode, "
        "JSONExtractString(coverage, 'boundary_key') AS boundary_key, "
        "coalesce(nullIf(JSONExtractString(coverage, 'replay_cutoff_value'), ''), "
        "JSONExtractString(coverage, 'upper_value')) AS cutoff_value, "
        "toString(boundary_time, 'UTC') AS boundary_time\n"
        "FROM latest_coverage\n"
        "ARRAY JOIN JSONExtractArrayRaw(value) AS coverage\n"
        "ORDER BY boundary_key;"
    )


def _read_final_ownership_sql(*, request: DirectBuildRequest) -> str:
    relation_names: tuple[str, ...] = _entry_relation_names(request=request)
    quoted_names: str = ", ".join(
        f"'{_escape_literal(relation_name)}'" for relation_name in relation_names
    )
    return (
        "SELECT database_name, relation_name, resource_kind, logical_model_database, "
        "logical_model_name, owning_mode, tool_version, replay_coverage_json "
        f"FROM {request.metadata_database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} FINAL "
        f"WHERE database_name = '{_escape_literal(request.database)}' "
        f"AND relation_name IN ({quoted_names}) ORDER BY relation_name;"
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


def _required_relation(*, snapshot: DirectWarehouseSnapshot, relation_name: str) -> CatalogRelation:
    relation: CatalogRelation | None = snapshot.catalog.relation(relation_name)
    if relation is None:
        raise DirectBuildError(f"Preserved source '{relation_name}' disappeared during assembly")
    return relation


def _terminate_sql(sql: str) -> str:
    return f"{sql.rstrip().rstrip(';')};"


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _step_segment(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)


def _typed_replay_value(*, replay_range: AdapterReplayCoverageRange, value: str) -> str:
    escaped_value: str = _escape_literal(value)
    if replay_range.replay_boundary_mode == AdapterReplayBoundaryMode.CURSOR:
        return f"toInt64('{escaped_value}')"
    return f"toDateTime64('{escaped_value}', 3, 'UTC')"


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
