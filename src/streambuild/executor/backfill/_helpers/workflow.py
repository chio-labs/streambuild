"""Assemble the authoritative virtual build workflow."""

from __future__ import annotations

import json
import math

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    DEPLOYMENT_BOUNDARY_TIME_KEY,
    METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_PUBLISH_HISTORY_TABLE_NAME,
    METADATA_TARGET_OWNERSHIP_TABLE_NAME,
)
from streambuild.adapter.models import (
    AdapterDeploymentRecord,
    AdapterDeploymentReplayRequest,
    AdapterMaterializedView,
    AdapterMetadataState,
    AdapterReplayRequest,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ExternalSourceReplayConfig,
    ObjectKey,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.executor.backfill._helpers.metadata import build_deployment_metadata_state
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.backfill.main.build_root_backfill_reports import (
    build_root_backfill_reports,
)
from streambuild.executor.backfill.models import BackfillBootstrapRequest, RootBackfillReport
from streambuild.executor.population.main._build_population_replay_templates import (
    build_population_replay_templates,
)
from streambuild.executor.population.main._expand_population_plan import expand_population_plan
from streambuild.executor.population.main._plan_population_objects import plan_population_objects
from streambuild.executor.population.main._plan_population_sources import plan_population_sources
from streambuild.executor.population.models import (
    PopulationObject,
    PopulationPlan,
    PopulationRealization,
    PopulationRoot,
    PopulationSourcePreparation,
)
from streambuild.executor.workflow.models import BuildWorkflow, WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowMode, WorkflowPhase


def assemble_virtual_build_workflow(
    *, request: BackfillBootstrapRequest, client: AdapterConnection, plan_json: str
) -> BuildWorkflow:
    """Resolve preconditions and assemble every virtual build statement once."""

    deployment_plan: DeploymentPlan = _confirmed_plan(request)
    deployment_id: str = _confirmed_deployment_id(request)
    target_catalog: CatalogSnapshot = _confirmed_catalog(
        catalog=request.confirmed_target_catalog,
        catalog_name="target",
    )
    metadata_catalog: CatalogSnapshot = _confirmed_catalog(
        catalog=request.confirmed_metadata_catalog,
        catalog_name="metadata",
    )
    root_reports: tuple[RootBackfillReport, ...] = build_root_backfill_reports(
        catalog=target_catalog,
        desired_state=request.desired_state,
    )
    source_preparation: PopulationSourcePreparation
    source_realizations: tuple[PopulationRealization, ...]
    source_preparation, source_realizations = plan_population_sources(
        desired_state=request.desired_state,
        default_database=request.default_database,
        existing_relation_names=target_catalog.relation_names(),
    )
    population_plan: PopulationPlan = expand_population_plan(
        plan=_population_plan(
            deployment_plan=deployment_plan,
            execution_id=deployment_id,
            replay_lineage_mode=str(request.replay_lineage_mode),
        ),
        desired_state=request.desired_state,
    )
    replay_templates: tuple[tuple[ObjectKey, AdapterReplayRequest], ...] = (
        build_population_replay_templates(
            plan=population_plan,
            desired_state=request.desired_state,
            default_database=request.default_database,
        )
    )
    metadata_state: AdapterMetadataState = build_deployment_metadata_state(
        deployment_plan=deployment_plan,
        desired_objects=request.desired_state.objects,
        deployment_id=deployment_id,
        created_at=_created_at(request),
        replay_lineage_mode=ReplayLineageMode(request.replay_lineage_mode),
        root_reports=root_reports,
    )
    statements: tuple[WarehouseStatement, ...] = _assemble_statements(
        request=request,
        client=client,
        target_catalog=target_catalog,
        metadata_catalog=metadata_catalog,
        metadata_state=metadata_state,
        source_preparation=source_preparation,
        source_realizations=source_realizations,
        population_plan=population_plan,
        replay_templates=replay_templates,
    )
    return BuildWorkflow(
        mode=WorkflowMode.VIRTUAL_ENVIRONMENT,
        plan_json=plan_json,
        statements=statements,
    )


def build_virtual_bootstrap_workflow(*, workflow: BuildWorkflow) -> BuildWorkflow:
    """Return the preflight, preparation, and ownership prefix used by bootstrap tests."""

    statements: tuple[WarehouseStatement, ...] = tuple(
        statement
        for statement in workflow.statements
        if statement.phase
        in {WorkflowPhase.PREFLIGHT, WorkflowPhase.PREPARATION, WorkflowPhase.OWNERSHIP}
    )
    return BuildWorkflow(mode=workflow.mode, plan_json=workflow.plan_json, statements=statements)


def _assemble_statements(
    *,
    request: BackfillBootstrapRequest,
    client: AdapterConnection,
    target_catalog: CatalogSnapshot,
    metadata_catalog: CatalogSnapshot,
    metadata_state: AdapterMetadataState,
    source_preparation: PopulationSourcePreparation,
    source_realizations: tuple[PopulationRealization, ...],
    population_plan: PopulationPlan,
    replay_templates: tuple[tuple[ObjectKey, AdapterReplayRequest], ...],
) -> tuple[WarehouseStatement, ...]:
    preflight: tuple[WarehouseStatement, ...] = _preflight_statements(
        request=request,
        target_catalog=target_catalog,
        metadata_catalog=metadata_catalog,
        metadata_state=metadata_state,
    )
    preparation: tuple[WarehouseStatement, ...] = _preparation_statements(
        request=request,
        client=client,
        source_realizations=source_realizations,
        start_sequence=len(preflight) + 1,
    )
    metadata: tuple[WarehouseStatement, ...] = _metadata_statements(
        request=request,
        client=client,
        metadata_state=metadata_state,
        start_sequence=len(preflight) + len(preparation) + 1,
    )
    realization: tuple[WarehouseStatement, ...] = _realization_statements(
        request=request,
        client=client,
        source_preparation=source_preparation,
        population_plan=population_plan,
        start_sequence=len(preflight) + len(preparation) + len(metadata) + 1,
    )
    stabilization: tuple[WarehouseStatement, ...] = _stabilization_statements(
        seconds=request.stabilization_seconds,
        start_sequence=len(preflight) + len(preparation) + len(metadata) + len(realization) + 1,
    )
    prior_count: int = sum(
        len(phase) for phase in (preflight, preparation, metadata, realization, stabilization)
    )
    boundary: tuple[WarehouseStatement, ...] = _boundary_statements(
        request=request,
        start_sequence=prior_count + 1,
    )
    replay: tuple[WarehouseStatement, ...] = _replay_statements(
        request=request,
        client=client,
        target_catalog=target_catalog,
        population_plan=population_plan,
        replay_templates=replay_templates,
        start_sequence=prior_count + len(boundary) + 1,
    )
    audit: tuple[WarehouseStatement, ...] = _audit_statements(
        request=request,
        replay_templates=replay_templates,
        start_sequence=prior_count + len(boundary) + len(replay) + 1,
    )
    return (
        *preflight,
        *preparation,
        *metadata,
        *realization,
        *stabilization,
        *boundary,
        *replay,
        *audit,
    )


def _preflight_statements(
    *,
    request: BackfillBootstrapRequest,
    target_catalog: CatalogSnapshot,
    metadata_catalog: CatalogSnapshot,
    metadata_state: AdapterMetadataState,
) -> tuple[WarehouseStatement, ...]:
    metadata_names: frozenset[str] = metadata_catalog.relation_names()
    rendered: list[tuple[str, str]] = [
        (
            "assert_virtual_ownership",
            _ownership_assertion_sql(
                request=request,
                ownership_table_exists=METADATA_TARGET_OWNERSHIP_TABLE_NAME in metadata_names,
            ),
        ),
        (
            "assert_candidate_metadata",
            _candidate_assertion_sql(
                request=request,
                metadata_state=metadata_state,
                deployments_table_exists=METADATA_DEPLOYMENTS_TABLE_NAME in metadata_names,
            ),
        ),
        (
            "assert_candidate_unpublished",
            _publish_assertion_sql(
                request=request,
                publish_table_exists=METADATA_PUBLISH_HISTORY_TABLE_NAME in metadata_names,
            ),
        ),
    ]
    prepared_name: str
    for prepared_name in _prepared_relation_names(request):
        relation: CatalogRelation | None = target_catalog.relation(prepared_name)
        rendered.append(
            (
                f"assert_candidate_relation_{_step_segment(prepared_name)}",
                _relation_assertion_sql(
                    database=request.default_database,
                    relation_name=prepared_name,
                    observed_relation=relation,
                ),
            )
        )
    return tuple(
        WarehouseStatement(
            sequence=index,
            step_id=step_id,
            phase=WorkflowPhase.PREFLIGHT,
            intent=StatementIntent.ASSERTION,
            sql=_terminate_sql(sql),
        )
        for index, (step_id, sql) in enumerate(rendered, start=1)
    )


def _preparation_statements(
    *,
    request: BackfillBootstrapRequest,
    client: AdapterConnection,
    source_realizations: tuple[PopulationRealization, ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    rendered: list[tuple[str, str]] = [
        ("prepare_target_database", client.render_ensure_database(request.default_database))
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
                client.render_resource(
                    resource=realization.resource,
                    database=realization.database,
                    if_not_exists=True,
                ),
            )
        )
    return _mutation_statements(
        rendered=tuple(rendered),
        phase=WorkflowPhase.PREPARATION,
        start_sequence=start_sequence,
    )


def _metadata_statements(
    *,
    request: BackfillBootstrapRequest,
    client: AdapterConnection,
    metadata_state: AdapterMetadataState,
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    rendered: tuple[tuple[str, str], ...] = tuple(
        (f"persist_candidate_metadata_{index}", sql)
        for index, sql in enumerate(
            client.render_persist_metadata_state(
                database=request.metadata_database,
                state=metadata_state,
            ),
            start=1,
        )
    )
    return _mutation_statements(
        rendered=rendered,
        phase=WorkflowPhase.OWNERSHIP,
        start_sequence=start_sequence,
    )


def _realization_statements(
    *,
    request: BackfillBootstrapRequest,
    client: AdapterConnection,
    source_preparation: PopulationSourcePreparation,
    population_plan: PopulationPlan,
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    realizations: tuple[PopulationRealization, ...] = plan_population_objects(
        plan=population_plan,
        desired_state=request.desired_state,
        default_database=request.default_database,
    )
    rendered: list[tuple[str, str]] = []
    realization: PopulationRealization
    for realization in realizations:
        rendered.append(
            (
                f"realize_{_step_segment(realization.resource.name)}",
                client.render_resource(
                    resource=realization.resource,
                    database=realization.database,
                    if_not_exists=True,
                ),
            )
        )
    landing_view: DesiredMaterializedView
    for landing_view in source_preparation.landing_views:
        built_resource: object = build_adapter_resource(landing_view)
        if not isinstance(built_resource, AdapterMaterializedView):
            raise BackfillExecutionError(
                f"Landing view '{landing_view.name}' did not realize as a materialized view"
            )
        resource: AdapterMaterializedView = built_resource
        rendered.append(
            (
                f"attach_source_{_step_segment(landing_view.name)}",
                client.render_resource(
                    resource=resource,
                    database=landing_view.key.database or request.default_database,
                    if_not_exists=True,
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
            step_id="wait_for_virtual_live_stabilization",
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
    request: BackfillBootstrapRequest,
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    return (
        WarehouseStatement(
            sequence=start_sequence,
            step_id="capture_boundary_time",
            phase=WorkflowPhase.BOUNDARY,
            intent=StatementIntent.MUTATION,
            sql=_boundary_time_capture_sql(request=request),
        ),
    )


def _replay_statements(
    *,
    request: BackfillBootstrapRequest,
    client: AdapterConnection,
    target_catalog: CatalogSnapshot,
    population_plan: PopulationPlan,
    replay_templates: tuple[tuple[ObjectKey, AdapterReplayRequest], ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = []
    root_by_key: dict[ObjectKey, PopulationRoot] = {
        root.root_key: root for root in population_plan.roots
    }
    root_key: ObjectKey
    replay: AdapterReplayRequest
    for root_key, replay in replay_templates:
        segment: str = _step_segment(root_key.name)
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"capture_watermark_{segment}",
                phase=WorkflowPhase.REPLAY,
                intent=StatementIntent.MUTATION,
                sql=_watermark_capture_sql(
                    request=request,
                    root=root_by_key[root_key],
                    replay=replay,
                ),
            )
        )
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"assert_qualifying_input_{segment}",
                phase=WorkflowPhase.REPLAY,
                intent=StatementIntent.ASSERTION,
                sql=_qualifying_input_assertion_sql(request=request, replay=replay),
            )
        )
        rendered: tuple[str, ...] = client.render_replay_from_deployment(
            AdapterDeploymentReplayRequest(
                replay=replay,
                metadata_database=request.metadata_database,
                deployment_id=_confirmed_deployment_id(request),
                boundary_column_type=_boundary_column_type(
                    desired_state=request.desired_state,
                    target_catalog=target_catalog,
                    replay=replay,
                    anchor_key=root_by_key[root_key].upstream_boundary_key,
                ),
                active_relation_name=_active_relation_name(
                    target_catalog=target_catalog,
                    replay=replay,
                ),
                active_column_names=_active_column_names(
                    target_catalog=target_catalog,
                    replay=replay,
                ),
                anchor_column_names=_anchor_column_names(
                    desired_state=request.desired_state,
                    target_catalog=target_catalog,
                    replay=replay,
                    anchor_key=root_by_key[root_key].upstream_boundary_key,
                ),
            )
        )
        sql_index: int
        sql: str
        for sql_index, sql in enumerate(rendered):
            is_replay: bool = sql_index == len(rendered) - 1
            statements.append(
                WarehouseStatement(
                    sequence=start_sequence + len(statements),
                    step_id=(
                        f"replay_{_step_segment(root_key.name)}"
                        if is_replay
                        else f"seed_{_step_segment(root_key.name)}"
                    ),
                    phase=WorkflowPhase.REPLAY,
                    intent=StatementIntent.MUTATION,
                    sql=_terminate_sql(sql),
                )
            )
    return tuple(statements)


def _audit_statements(
    *,
    request: BackfillBootstrapRequest,
    replay_templates: tuple[tuple[ObjectKey, AdapterReplayRequest], ...],
    start_sequence: int,
) -> tuple[WarehouseStatement, ...]:
    statements: list[WarehouseStatement] = []
    root_key: ObjectKey
    replay: AdapterReplayRequest
    for root_key, replay in replay_templates:
        segment: str = _step_segment(root_key.name)
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"read_readiness_{segment}",
                phase=WorkflowPhase.AUDIT,
                intent=StatementIntent.QUERY,
                sql=(
                    "SELECT count() AS staged_row_count, "
                    f"'{_escape_literal(replay.relations.target)}' AS staged_relation_name "
                    f"FROM {replay.database}.{replay.relations.target};"
                ),
            )
        )
        statements.append(
            WarehouseStatement(
                sequence=start_sequence + len(statements),
                step_id=f"assert_readiness_{segment}",
                phase=WorkflowPhase.AUDIT,
                intent=StatementIntent.ASSERTION,
                sql=(
                    "SELECT throwIf(count() != 1, 'Virtual candidate target is not ready') "
                    "FROM system.tables "
                    f"WHERE database = '{_escape_literal(replay.database)}' "
                    f"AND name = '{_escape_literal(replay.relations.target)}';"
                ),
            )
        )
    statements.append(
        WarehouseStatement(
            sequence=start_sequence + len(statements),
            step_id="read_boundary_time",
            phase=WorkflowPhase.AUDIT,
            intent=StatementIntent.QUERY,
            sql=_read_boundary_time_sql(request=request),
        )
    )
    return tuple(statements)


def _population_plan(
    *, deployment_plan: DeploymentPlan, execution_id: str, replay_lineage_mode: str
) -> PopulationPlan:
    return PopulationPlan(
        execution_id=execution_id,
        roots=tuple(
            PopulationRoot(
                root_key=subtree.root_key,
                affected_keys=subtree.affected_keys,
                upstream_boundary_key=subtree.upstream_boundary_key,
                replay_lineage_mode=replay_lineage_mode,
                execution_mode=subtree.execution_mode,
                forced_start_time=subtree.forced_start_time,
                execution_lookback_seconds=subtree.execution_lookback_seconds,
            )
            for subtree in deployment_plan.rebuild_subtrees
            if subtree.replay_required
        ),
        objects=tuple(
            PopulationObject(
                logical_key=prepared.logical_key,
                physical_name=prepared.physical_name,
            )
            for prepared in deployment_plan.prepared_shadow_objects
        ),
    )


def _ownership_assertion_sql(
    *, request: BackfillBootstrapRequest, ownership_table_exists: bool
) -> str:
    relation_names: tuple[str, ...] = tuple(
        object_.name for object_ in request.desired_state.objects
    )
    if not ownership_table_exists:
        return (
            "SELECT throwIf(count() != 0, 'Direct ownership metadata appeared after virtual "
            "confirmation') FROM system.tables "
            f"WHERE database = '{_escape_literal(request.metadata_database)}' "
            f"AND name = '{METADATA_TARGET_OWNERSHIP_TABLE_NAME}'"
        )
    quoted_names: str = ", ".join(f"'{_escape_literal(name)}'" for name in relation_names)
    return (
        "SELECT throwIf(countIf(owning_mode = 'direct') > 0, "
        "'Virtual build conflicts with direct-owned targets') "
        f"FROM {request.metadata_database}.{METADATA_TARGET_OWNERSHIP_TABLE_NAME} FINAL "
        f"WHERE database_name = '{_escape_literal(request.default_database)}' "
        f"AND relation_name IN ({quoted_names})"
    )


def _candidate_assertion_sql(
    *,
    request: BackfillBootstrapRequest,
    metadata_state: AdapterMetadataState,
    deployments_table_exists: bool,
) -> str:
    if not deployments_table_exists:
        return (
            "SELECT throwIf(count() != 0, 'Candidate metadata appeared after virtual "
            "confirmation') FROM system.tables "
            f"WHERE database = '{_escape_literal(request.metadata_database)}' "
            f"AND name = '{METADATA_DEPLOYMENTS_TABLE_NAME}'"
        )
    deployment: AdapterDeploymentRecord = metadata_state.deployments[0]
    selected_json: str = json.dumps(
        [
            {"database": key.database, "object_type": key.object_type, "name": key.name}
            for key in deployment.selected_root_keys
        ]
    )
    warning_json: str = json.dumps(list(deployment.warning_codes))
    mappings_json: str = json.dumps(
        [
            {
                "logical_key": {
                    "database": mapping.logical_key.database,
                    "object_type": mapping.logical_key.object_type,
                    "name": mapping.logical_key.name,
                },
                "physical_name": mapping.physical_name,
                "logical_model_name": mapping.logical_model_name,
            }
            for mapping in deployment.prepared_object_mappings
        ]
    )
    return (
        "SELECT throwIf(count() > 0 AND (count() != 1 OR "
        f"any(created_at) != toDateTime64('{_escape_literal(deployment.created_at)}', 3, 'UTC') OR "
        f"any(status) != '{_escape_literal(deployment.status)}' OR "
        f"any(replay_lineage_mode) != '{_escape_literal(deployment.replay_lineage_mode)}' OR "
        f"any(selected_root_keys_json) != '{_escape_literal(selected_json)}' OR "
        f"any(warning_codes_json) != '{_escape_literal(warning_json)}' OR "
        f"any(prepared_object_mappings_json) != '{_escape_literal(mappings_json)}'), "
        "'Candidate deployment conflicts with the confirmed workflow') "
        f"FROM {request.metadata_database}.{METADATA_DEPLOYMENTS_TABLE_NAME} FINAL "
        f"WHERE deployment_id = '{_escape_literal(deployment.deployment_id)}'"
    )


def _publish_assertion_sql(*, request: BackfillBootstrapRequest, publish_table_exists: bool) -> str:
    if not publish_table_exists:
        return (
            "SELECT throwIf(count() != 0, 'Publish metadata appeared after virtual "
            "confirmation') FROM system.tables "
            f"WHERE database = '{_escape_literal(request.metadata_database)}' "
            f"AND name = '{METADATA_PUBLISH_HISTORY_TABLE_NAME}'"
        )
    return (
        "SELECT throwIf(count() > 0, 'Candidate deployment is already published') "
        f"FROM {request.metadata_database}.{METADATA_PUBLISH_HISTORY_TABLE_NAME} "
        f"WHERE deployment_id = '{_escape_literal(_confirmed_deployment_id(request))}'"
    )


def _relation_assertion_sql(
    *, database: str, relation_name: str, observed_relation: CatalogRelation | None
) -> str:
    if observed_relation is None:
        return (
            "SELECT throwIf(count() != 0, 'Candidate relation appeared after virtual "
            "confirmation') FROM system.tables "
            f"WHERE database = '{_escape_literal(database)}' "
            f"AND name = '{_escape_literal(relation_name)}'"
        )
    definition_sql: str = observed_relation.definition_sql or ""
    return (
        "SELECT throwIf(count() != 1 OR any(create_table_query) != "
        f"'{_escape_literal(definition_sql)}', 'Candidate relation changed after virtual "
        "confirmation') FROM system.tables "
        f"WHERE database = '{_escape_literal(database)}' "
        f"AND name = '{_escape_literal(relation_name)}'"
    )


def _boundary_time_capture_sql(*, request: BackfillBootstrapRequest) -> str:
    boundary_expression: str = (
        f"toDateTime64('{_escape_literal(request.boundary_time)}', 3, 'UTC')"
        if request.boundary_time is not None
        else "now64(3, 'UTC')"
    )
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} "
        "(deployment_id, root_database_name, root_object_type, root_object_name, "
        "anchor_database_name, anchor_object_type, anchor_object_name, boundary_key, "
        "cutoff_value)\n"
        f"SELECT '{_escape_literal(_confirmed_deployment_id(request))}', "
        "NULL, 'table', '', NULL, 'table', '', "
        f"'{DEPLOYMENT_BOUNDARY_TIME_KEY}', toString({boundary_expression}, 'UTC')\n"
        "WHERE NOT EXISTS (SELECT 1 FROM "
        f"{request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} FINAL "
        f"WHERE deployment_id = '{_escape_literal(_confirmed_deployment_id(request))}' "
        f"AND boundary_key = '{DEPLOYMENT_BOUNDARY_TIME_KEY}' "
        "AND cutoff_value != '');"
    )


def _watermark_capture_sql(
    *, request: BackfillBootstrapRequest, root: PopulationRoot, replay: AdapterReplayRequest
) -> str:
    if replay.mode == AdapterReplayBoundaryMode.OFFSETS:
        return _offset_watermark_capture_sql(request=request, root=root, replay=replay)
    return _scalar_watermark_capture_sql(request=request, root=root, replay=replay)


def _offset_watermark_capture_sql(
    *, request: BackfillBootstrapRequest, root: PopulationRoot, replay: AdapterReplayRequest
) -> str:
    boundary_time: str = _boundary_time_subquery(request=request, replay=replay)
    boundary_predicate: str = (
        f"\nWHERE {replay.columns.landed_at or replay.columns.timestamp} <= {boundary_time}"
        if root.persist_watermarks
        else ""
    )
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} "
        "(deployment_id, root_database_name, root_object_type, root_object_name, "
        "anchor_database_name, anchor_object_type, anchor_object_name, boundary_key, "
        "cutoff_value)\n"
        f"SELECT '{_escape_literal(_confirmed_deployment_id(request))}', "
        f"{_nullable_literal(replay.database)}, 'table', "
        f"'{_escape_literal(replay.relations.root)}', {_nullable_literal(replay.database)}, "
        f"'table', '{_escape_literal(replay.relations.anchor)}', "
        f"concat('_replay_partition=', toString({replay.columns.partition})), "
        f"toString(max({replay.columns.offset}))\n"
        f"FROM {replay.database}.{replay.relations.anchor}{boundary_predicate}\n"
        f"GROUP BY {replay.columns.partition}\n"
        "HAVING NOT EXISTS (SELECT 1 FROM "
        f"{request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} FINAL "
        f"WHERE deployment_id = '{_escape_literal(_confirmed_deployment_id(request))}' "
        f"AND root_object_name = '{_escape_literal(replay.relations.root)}' "
        "AND startsWith(boundary_key, '_replay_partition='));"
    )


def _scalar_watermark_capture_sql(
    *, request: BackfillBootstrapRequest, root: PopulationRoot, replay: AdapterReplayRequest
) -> str:
    boundary_key: str = _canonical_boundary_key(replay.mode)
    cutoff_expression: str = (
        f"toString(max({replay.columns.cursor}))"
        if replay.mode == AdapterReplayBoundaryMode.CURSOR
        else f"toString({_boundary_time_subquery(request=request, replay=replay)}, 'UTC')"
    )
    return (
        f"INSERT INTO {request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} "
        "(deployment_id, root_database_name, root_object_type, root_object_name, "
        "anchor_database_name, anchor_object_type, anchor_object_name, boundary_key, "
        "cutoff_value)\n"
        f"SELECT '{_escape_literal(_confirmed_deployment_id(request))}', "
        f"{_nullable_literal(replay.database)}, 'table', "
        f"'{_escape_literal(replay.relations.root)}', "
        f"{_nullable_literal(root.upstream_boundary_key.database)}, "
        f"'{_escape_literal(str(root.upstream_boundary_key.object_type))}', "
        f"'{_escape_literal(root.upstream_boundary_key.name)}', "
        f"'{boundary_key}', {cutoff_expression}\n"
        f"FROM {replay.database}.{replay.relations.anchor}\n"
        "HAVING count() > 0 AND NOT EXISTS (SELECT 1 FROM "
        f"{request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} FINAL "
        f"WHERE deployment_id = '{_escape_literal(_confirmed_deployment_id(request))}' "
        f"AND root_object_name = '{_escape_literal(replay.relations.root)}' "
        f"AND boundary_key = '{boundary_key}');"
    )


def _qualifying_input_assertion_sql(
    *, request: BackfillBootstrapRequest, replay: AdapterReplayRequest
) -> str:
    if replay.mode == AdapterReplayBoundaryMode.OFFSETS:
        qualifying: str = (
            "SELECT count() FROM "
            f"{replay.database}.{replay.relations.anchor} AS source INNER JOIN "
            f"(SELECT * FROM {request.metadata_database}."
            f"{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} FINAL) AS watermark "
            "ON watermark.deployment_id = "
            f"'{_escape_literal(_confirmed_deployment_id(request))}' "
            f"AND watermark.root_object_name = '{_escape_literal(replay.relations.root)}' "
            "AND watermark.boundary_key = concat('_replay_partition=', "
            f"toString(source.{replay.columns.partition})) WHERE "
            f"source.{replay.columns.offset} <= toInt64(watermark.cutoff_value)"
        )
    else:
        boundary_key: str = _canonical_boundary_key(replay.mode)
        boundary_column: str = {
            AdapterReplayBoundaryMode.CURSOR: replay.columns.cursor,
            AdapterReplayBoundaryMode.TIMESTAMP: replay.columns.timestamp,
            AdapterReplayBoundaryMode.LANDED_AT: replay.columns.landed_at,
        }[replay.mode]
        qualifying = (
            f"SELECT count() FROM {replay.database}.{replay.relations.anchor} AS source "
            f"CROSS JOIN (SELECT * FROM {request.metadata_database}."
            f"{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} FINAL) AS watermark "
            "WHERE watermark.deployment_id = "
            f"'{_escape_literal(_confirmed_deployment_id(request))}' "
            f"AND watermark.root_object_name = '{_escape_literal(replay.relations.root)}' "
            f"AND watermark.boundary_key = '{boundary_key}' AND source.{boundary_column} <= "
            f"CAST(watermark.cutoff_value AS {_boundary_type_expression(replay.mode)})"
        )
    return (
        "SELECT throwIf(total_rows > 0 AND qualifying_rows = 0, "
        f"'Replay root {_escape_literal(replay.relations.root)} has rows but no "
        f"qualifying {_escape_literal(str(replay.mode))} cutoff') FROM (SELECT "
        f"(SELECT count() FROM {replay.database}.{replay.relations.anchor}) AS total_rows, "
        f"({qualifying}) AS qualifying_rows);"
    )


def _read_boundary_time_sql(*, request: BackfillBootstrapRequest) -> str:
    return (
        "SELECT any(cutoff_value) AS boundary_time "
        f"FROM {request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} FINAL "
        f"WHERE deployment_id = '{_escape_literal(_confirmed_deployment_id(request))}' "
        f"AND boundary_key = '{DEPLOYMENT_BOUNDARY_TIME_KEY}';"
    )


def _boundary_time_subquery(
    *, request: BackfillBootstrapRequest, replay: AdapterReplayRequest
) -> str:
    return (
        "(SELECT toDateTime64(cutoff_value, 3, 'UTC') FROM "
        f"{request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} FINAL "
        f"WHERE deployment_id = '{_escape_literal(_confirmed_deployment_id(request))}' "
        f"AND boundary_key = '{DEPLOYMENT_BOUNDARY_TIME_KEY}')"
    )


def _boundary_column_type(
    *,
    desired_state: DesiredState,
    target_catalog: CatalogSnapshot,
    replay: AdapterReplayRequest,
    anchor_key: ObjectKey,
) -> str | None:
    if replay.mode == AdapterReplayBoundaryMode.OFFSETS:
        return None
    position_column: str = {
        AdapterReplayBoundaryMode.CURSOR: replay.columns.cursor,
        AdapterReplayBoundaryMode.TIMESTAMP: replay.columns.timestamp,
        AdapterReplayBoundaryMode.LANDED_AT: replay.columns.landed_at,
    }[replay.mode]
    desired: DesiredTable
    for desired in (item for item in desired_state.objects if isinstance(item, DesiredTable)):
        if desired.key == anchor_key:
            return next(column.type for column in desired.columns if column.name == position_column)
    relation: CatalogRelation | None = target_catalog.relation(replay.relations.anchor)
    if relation is not None:
        return next(column.type for column in relation.columns if column.name == position_column)
    external: ExternalSourceReplayConfig
    for external in desired_state.external_source_replay_configs:
        if external.table_name == replay.relations.anchor:
            source_relation: CatalogRelation | None = target_catalog.relation(external.table_name)
            if source_relation is not None:
                return next(
                    column.type
                    for column in source_relation.columns
                    if column.name == position_column
                )
    return _boundary_type_expression(replay.mode)


def _active_column_names(
    *, target_catalog: CatalogSnapshot, replay: AdapterReplayRequest
) -> tuple[str, ...]:
    relation: CatalogRelation | None = target_catalog.relation(
        _active_relation_name(target_catalog=target_catalog, replay=replay)
    )
    return () if relation is None else tuple(column.name for column in relation.columns)


def _active_relation_name(*, target_catalog: CatalogSnapshot, replay: AdapterReplayRequest) -> str:
    relation: CatalogRelation | None = target_catalog.relation(replay.relations.root)
    if relation is None or relation.stable_binding_name is None:
        return replay.relations.root
    return relation.stable_binding_name


def _anchor_column_names(
    *,
    desired_state: DesiredState,
    target_catalog: CatalogSnapshot,
    replay: AdapterReplayRequest,
    anchor_key: ObjectKey,
) -> tuple[str, ...]:
    desired: DesiredTable
    for desired in (item for item in desired_state.objects if isinstance(item, DesiredTable)):
        if desired.key == anchor_key:
            return tuple(column.name for column in desired.columns)
    relation: CatalogRelation | None = target_catalog.relation(replay.relations.anchor)
    return () if relation is None else tuple(column.name for column in relation.columns)


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


def _confirmed_plan(request: BackfillBootstrapRequest) -> DeploymentPlan:
    if request.confirmed_plan is None:
        raise BackfillExecutionError(
            "Virtual workflow assembly requires the confirmed deployment plan"
        )
    return request.confirmed_plan


def _confirmed_deployment_id(request: BackfillBootstrapRequest) -> str:
    plan: DeploymentPlan = _confirmed_plan(request)
    if request.deployment_id is None or plan.deployment_id != request.deployment_id:
        raise BackfillExecutionError(
            "Virtual workflow deployment identity does not match the confirmed plan"
        )
    return request.deployment_id


def _created_at(request: BackfillBootstrapRequest) -> str:
    if request.created_at is None:
        raise BackfillExecutionError(
            "Virtual workflow assembly requires a fixed creation timestamp"
        )
    return request.created_at


def _confirmed_catalog(*, catalog: CatalogSnapshot | None, catalog_name: str) -> CatalogSnapshot:
    if catalog is None:
        raise BackfillExecutionError(
            f"Virtual workflow assembly requires the pre-confirmation {catalog_name} catalog"
        )
    return catalog


def _prepared_relation_names(request: BackfillBootstrapRequest) -> tuple[str, ...]:
    return tuple(
        prepared.physical_name for prepared in _confirmed_plan(request).prepared_shadow_objects
    )


def _canonical_boundary_key(mode: AdapterReplayBoundaryMode) -> str:
    return {
        AdapterReplayBoundaryMode.CURSOR: "_replay_cursor",
        AdapterReplayBoundaryMode.TIMESTAMP: "_replay_timestamp",
        AdapterReplayBoundaryMode.LANDED_AT: "_replay_landed_at",
    }[mode]


def _boundary_type_expression(mode: AdapterReplayBoundaryMode) -> str:
    return "UInt64" if mode == AdapterReplayBoundaryMode.CURSOR else "DateTime64(3, 'UTC')"


def _nullable_literal(value: str | None) -> str:
    return "NULL" if value is None else f"'{_escape_literal(value)}'"


def _terminate_sql(sql: str) -> str:
    return f"{sql.rstrip().rstrip(';')};"


def _escape_literal(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _step_segment(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)
