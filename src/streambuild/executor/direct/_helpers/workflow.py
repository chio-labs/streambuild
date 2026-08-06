"""Assemble the complete authoritative direct build workflow."""

from __future__ import annotations

import math
from hashlib import sha256

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    METADATA_DIRECT_FINGERPRINTS_TABLE_NAME,
    METADATA_DIRECT_REPLAY_CHECKPOINTS_TABLE_NAME,
    METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME,
)
from streambuild.adapter.models import (
    AdapterCheckpointReplayRequest,
    AdapterMaterializedView,
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
from streambuild.compiler.planner.main.load_direct_warehouse_snapshot import (
    load_direct_warehouse_snapshot,
)
from streambuild.compiler.planner.models import (
    DirectPlanEntry,
    DirectRelationOperation,
    DirectWarehouseSnapshot,
)
from streambuild.compiler.planner.types import DirectResourceKind
from streambuild.executor.auditing.constants import AUDIT_SAMPLE_LIMIT
from streambuild.executor.auditing.types import AuditSeverity
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
    )
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
    statements: tuple[WarehouseStatement, ...] = _assemble_statements(
        request=request,
        client=client,
        snapshot=snapshot,
        source_preparation=source_preparation,
        source_realizations=source_realizations,
        realizations=realizations,
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
    realizations: tuple[PopulationRealization, ...],
    replay_templates: tuple[AdapterReplayRequest, ...],
) -> tuple[WarehouseStatement, ...]:
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
    preparation: tuple[WarehouseStatement, ...] = _preparation_statements(
        request=request,
        client=client,
        source_realizations=source_realizations,
        start_sequence=1,
    )
    teardown: tuple[WarehouseStatement, ...] = _teardown_statements(
        request=request,
        start_sequence=len(preparation) + 1,
    )
    realization: tuple[WarehouseStatement, ...] = _realization_statements(
        request=request,
        client=client,
        rendered_realizations=rendered_realizations,
        source_preparation=source_preparation,
        start_sequence=len(preparation) + len(teardown) + 1,
    )
    stabilization: tuple[WarehouseStatement, ...] = _stabilization_statements(
        seconds=request.stabilization_seconds,
        start_sequence=(len(preparation) + len(teardown) + len(realization) + 1),
    )
    prior_count: int = sum(
        len(phase) for phase in (preparation, teardown, realization, stabilization)
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
    fingerprints: tuple[WarehouseStatement, ...] = _fingerprint_statements(
        request=request,
        rendered_realizations=rendered_realizations,
        start_sequence=prior_count + len(boundary) + len(replay) + len(audit) + 1,
    )
    return (
        *preparation,
        *teardown,
        *realization,
        *stabilization,
        *boundary,
        *replay,
        *audit,
        *fingerprints,
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
    rendered_realizations: tuple[tuple[PopulationRealization, str], ...],
    source_preparation: PopulationSourcePreparation,
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
                    client.render_replay_from_checkpoint(
                        AdapterCheckpointReplayRequest(
                            replay=replay,
                            metadata_database=request.metadata_database,
                            checkpoint_id=_checkpoint_id(request=request, model_name=model_name),
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


def _fingerprint_statements(
    *,
    request: DirectBuildRequest,
    rendered_realizations: tuple[tuple[PopulationRealization, str], ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = []
    for entry in request.plan.entries:
        for relation_name, resource_kind in zip(
            entry.relation_names, entry.resource_kinds, strict=True
        ):
            rendered_definition: str = next(
                definition
                for realization, definition in rendered_realizations
                if realization.database == request.database
                and realization.resource.name == relation_name
            )
            rendered_definition_hash: str = sha256(rendered_definition.encode()).hexdigest()
            logical_identity: str = f"{request.database}.{entry.model_key.name}"
            audit_gate: str = " AND ".join(
                f"NOT EXISTS (\n{audit.query}\n)"
                for audit in request.audits
                if audit.severity == AuditSeverity.ERROR
            )
            statements.append(
                WarehouseStatement(
                    sequence=start_sequence + len(statements),
                    step_id=f"record_direct_fingerprint_{_step_segment(relation_name)}",
                    phase=WorkflowPhase.FINALIZATION,
                    intent=StatementIntent.MUTATION,
                    sql=_fingerprint_insert_sql(
                        request=request,
                        logical_identity=logical_identity,
                        relation_name=relation_name,
                        resource_kind=str(resource_kind),
                        rendered_definition_hash=rendered_definition_hash,
                        audit_gate=audit_gate,
                    ),
                )
            )
    return tuple(statements)


def _fingerprint_insert_sql(
    *,
    request: DirectBuildRequest,
    logical_identity: str,
    relation_name: str,
    resource_kind: str,
    rendered_definition_hash: str,
    audit_gate: str,
) -> str:
    values: tuple[str, ...] = (
        logical_identity,
        request.database,
        relation_name,
        resource_kind,
        rendered_definition_hash,
        request.workflow_id,
        request.tool_version,
    )
    fingerprint_parts: str = ", ".join(
        (
            *(f"'{_escape_literal(value)}'" for value in values[:4]),
            "create_table_query",
            f"'{_escape_literal(rendered_definition_hash)}'",
            "schema_fingerprint",
            *(f"'{_escape_literal(value)}'" for value in values[5:]),
        )
    )
    where_gate: str = "" if not audit_gate else f" AND {audit_gate}"
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_DIRECT_FINGERPRINTS_TABLE_NAME} "
        "(fingerprint_id, logical_model_identity, physical_database, physical_relation, "
        "resource_kind, definition_sql, definition_hash, rendered_definition_hash, "
        "schema_fingerprint, workflow_id, tool_version, succeeded_at)\n"
        "WITH (SELECT lower(hex(SHA256(toJSONString(arraySort(groupArray(tuple("
        "position, name, type, default_kind, default_expression))))))) FROM system.columns "
        f"WHERE database = '{_escape_literal(request.database)}' "
        f"AND table = '{_escape_literal(relation_name)}') AS schema_fingerprint\n"
        f"SELECT lower(hex(SHA256(concat({fingerprint_parts})))), "
        f"'{_escape_literal(logical_identity)}', '{_escape_literal(request.database)}', "
        f"'{_escape_literal(relation_name)}', '{_escape_literal(resource_kind)}', "
        "create_table_query, lower(hex(SHA256(create_table_query))), "
        f"'{_escape_literal(rendered_definition_hash)}', schema_fingerprint, "
        f"'{_escape_literal(request.workflow_id)}', '{_escape_literal(request.tool_version)}', "
        "now64(3, 'UTC') FROM system.tables "
        f"WHERE database = '{_escape_literal(request.database)}' "
        f"AND name = '{_escape_literal(relation_name)}'{where_gate};"
    )


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
    checkpoint_sequence: int = {
        "capture_boundary": 1,
        "refresh_boundary": 2,
        "refresh_coverage": 3,
    }[step_prefix]
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
                checkpoint_sequence=checkpoint_sequence,
            ),
        ),
        WarehouseStatement(
            sequence=start_sequence + 1,
            step_id=f"{step_prefix}_{segment}_checkpoint",
            phase=phase,
            intent=StatementIntent.MUTATION,
            sql=_refresh_checkpoint_sql(
                request=request,
                model_name=model_name,
                checkpoint_sequence=checkpoint_sequence,
            ),
        ),
    )


def _capture_replay_set_sql(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    snapshot: DirectWarehouseSnapshot,
    replay: AdapterReplayRequest,
    model_name: str,
    checkpoint_sequence: int,
) -> str:
    coverage_query: str = client.render_replay_coverage_query(
        _coverage_request(request=request, replay=replay, snapshot=snapshot)
    )
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        "(capture_id, replay_set_id, workflow_id, checkpoint_sequence, "
        "target_database_name, logical_model_database, logical_model_name, "
        "range_present, "
        "driving_input_relation_name, replay_boundary_mode, partition_value, "
        "source_partition_column_name, source_position_column_name, "
        "source_timestamp_column_name, lower_value, upper_value, replay_cutoff_value, "
        "captured_at)\n"
        f"WITH coverage_payload AS (\n{coverage_query}\n),\n"
        "captured_payload AS (SELECT value, now64(9, 'UTC') AS captured_at "
        "FROM coverage_payload),\n"
        "captured AS (SELECT value, lower(hex(SHA256(concat("
        f"'{_escape_literal(request.database)}', ':', '{_escape_literal(model_name)}', ':', "
        "value)))) AS replay_set_id, lower(hex(SHA256(concat("
        f"'{_escape_literal(request.workflow_id)}', ':', "
        f"'{checkpoint_sequence}', ':', toString(captured_at), ':', value)))) AS capture_id, "
        "captured_at FROM captured_payload)\n"
        f"SELECT capture_id, replay_set_id, '{_escape_literal(request.workflow_id)}', "
        f"{checkpoint_sequence}, '{_escape_literal(request.database)}', NULL, "
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


def _refresh_checkpoint_sql(
    *, request: DirectBuildRequest, model_name: str, checkpoint_sequence: int
) -> str:
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_DIRECT_REPLAY_CHECKPOINTS_TABLE_NAME} "
        "(checkpoint_id, workflow_id, target_database_name, logical_model_name, "
        "capture_id, replay_set_id, checkpoint_sequence, recorded_at)\n"
        "WITH latest_set AS (SELECT argMax(tuple(replay_set_id, captured_at, capture_id), "
        "tuple(captured_at, capture_id)) AS current_set FROM "
        f"{request.metadata_database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        f"WHERE target_database_name = '{_escape_literal(request.database)}' "
        f"AND logical_model_name = '{_escape_literal(model_name)}' "
        f"AND workflow_id = '{_escape_literal(request.workflow_id)}' "
        f"AND checkpoint_sequence = {checkpoint_sequence})\n"
        f"SELECT '{_escape_literal(_checkpoint_id(request=request, model_name=model_name))}', "
        f"'{_escape_literal(request.workflow_id)}', '{_escape_literal(request.database)}', "
        f"'{_escape_literal(model_name)}', current_set.3, current_set.1, "
        f"{checkpoint_sequence}, current_set.2 "
        "FROM latest_set;"
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
        "WITH current_checkpoint AS (SELECT argMax(tuple(replay_set_id, capture_id), "
        "tuple(recorded_at, capture_id)) AS current_set FROM "
        f"{request.metadata_database}.{METADATA_DIRECT_REPLAY_CHECKPOINTS_TABLE_NAME} "
        f"WHERE checkpoint_id = '{_checkpoint_id(request=request, model_name=model_name)}' "
        "AND checkpoint_sequence = 2)\n"
        f"SELECT DISTINCT '{_escape_literal(model_name)}' AS model_name, "
        f"driving_input_relation_name, replay_boundary_mode, {boundary_key} AS boundary_key, "
        "replay_cutoff_value AS cutoff_value FROM "
        f"{request.metadata_database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        "INNER JOIN current_checkpoint ON replay_set_id = current_checkpoint.current_set.1 "
        "AND capture_id = current_checkpoint.current_set.2 "
        f"WHERE target_database_name = '{_escape_literal(request.database)}' AND range_present "
        "ORDER BY boundary_key;"
    )


def _direct_boundary_key(mode: AdapterReplayBoundaryMode) -> str:
    return {
        AdapterReplayBoundaryMode.TIMESTAMP: "_replay_timestamp",
        AdapterReplayBoundaryMode.LANDED_AT: "_replay_landed_at",
        AdapterReplayBoundaryMode.CURSOR: "_replay_cursor",
    }[mode]


def _checkpoint_id(*, request: DirectBuildRequest, model_name: str) -> str:
    return f"{request.workflow_id}:{model_name}"


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
