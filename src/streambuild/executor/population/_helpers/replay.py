"""Build and execute replay requests for shared population."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterPhysicalRelationMapping,
    AdapterQueryResult,
    AdapterReplayBoundary,
    AdapterReplayColumns,
    AdapterReplayQuery,
    AdapterReplayRelations,
    AdapterReplayRequest,
    AdapterReplayResult,
    AdapterReplayWindow,
)
from streambuild.adapter.types import (
    AdapterReplayBoundaryMode,
    AdapterReplayLowerBoundMode,
    AdapterReplaySeedMode,
)
from streambuild.compiler.compile.constants import (
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ExternalSourceReplayConfig,
    ObjectKey,
)
from streambuild.compiler.planner.constants import (
    REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
)
from streambuild.compiler.planner.main.build_adapter_replay_query import build_adapter_replay_query
from streambuild.executor.population.exceptions import PopulationExecutionError
from streambuild.executor.population.models import (
    PopulationPlan,
    PopulationReplayExecution,
    PopulationRoot,
    PopulationWatermark,
)


def execute_population_replay(
    *,
    client: AdapterConnection,
    plan: PopulationPlan,
    desired_state: DesiredState,
    default_database: str,
    watermarks: tuple[PopulationWatermark, ...],
    boundary_time: str,
) -> tuple[tuple[PopulationReplayExecution, ...], tuple[ObjectKey, ...]]:
    """Execute every populated root through one request builder."""

    requests: tuple[tuple[ObjectKey, AdapterReplayRequest], ...] = _build_replay_requests(
        plan=plan,
        desired_state=desired_state,
        default_database=default_database,
        watermarks=watermarks,
        boundary_time=boundary_time,
    )
    request_by_root_key: dict[ObjectKey, AdapterReplayRequest] = dict(requests)
    executions: list[PopulationReplayExecution] = []
    root: PopulationRoot
    for root in plan.roots:
        if not _root_has_qualifying_replay_input(
            client=client,
            root=root,
            plan=plan,
            desired_state=desired_state,
            default_database=default_database,
            watermarks=watermarks,
            boundary_time=boundary_time,
        ):
            continue
        request: AdapterReplayRequest = request_by_root_key[root.root_key]
        result: AdapterReplayResult = client.execute_replay(request)
        executions.append(
            PopulationReplayExecution(root_key=root.root_key, written_rows=result.written_rows)
        )
    completed_keys: tuple[ObjectKey, ...] = tuple(execution.root_key for execution in executions)
    return tuple(executions), completed_keys


def _build_replay_requests(
    *,
    plan: PopulationPlan,
    desired_state: DesiredState,
    default_database: str,
    watermarks: tuple[PopulationWatermark, ...],
    boundary_time: str,
) -> tuple[tuple[ObjectKey, AdapterReplayRequest], ...]:
    physical_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name for prepared in plan.objects
    }
    root_table_by_key: dict[ObjectKey, DesiredTable] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
    }
    materialized_view_by_target: dict[str, DesiredMaterializedView] = {
        object_.target_table_name: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredMaterializedView)
    }
    physical_mappings: tuple[AdapterPhysicalRelationMapping, ...] = tuple(
        AdapterPhysicalRelationMapping(
            logical_name=object_.name,
            physical_name=physical_name_by_key.get(object_.key, object_.name),
        )
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
    )
    requests: list[tuple[ObjectKey, AdapterReplayRequest]] = []
    root: PopulationRoot
    for root in plan.roots:
        root_watermarks: tuple[PopulationWatermark, ...] = tuple(
            watermark for watermark in watermarks if watermark.root_key == root.root_key
        )
        if not root_watermarks:
            continue
        root_table: DesiredTable = root_table_by_key[root.root_key]
        view: DesiredMaterializedView = materialized_view_by_target[root_table.name]
        database: str = root_table.key.database or default_database
        external_config: ExternalSourceReplayConfig | None = _external_source_config(
            desired_state=desired_state, key=root.upstream_boundary_key
        )
        mode: AdapterReplayBoundaryMode = AdapterReplayBoundaryMode(root.replay_lineage_mode)
        replay_query: AdapterReplayQuery = build_adapter_replay_query(
            query=view.query,
            source_relation_name=view.source_table_name,
            database=database,
            physical_relation_mappings=physical_mappings,
        )
        requests.append(
            (
                root.root_key,
                AdapterReplayRequest(
                    mode=mode,
                    database=database,
                    relations=AdapterReplayRelations(
                        root=root_table.name,
                        source=view.source_table_name,
                        anchor=physical_name_by_key.get(
                            root.upstream_boundary_key, root.upstream_boundary_key.name
                        ),
                        target=physical_name_by_key[root.root_key],
                    ),
                    replay_query=replay_query,
                    boundaries=_adapter_boundaries(mode=mode, watermarks=root_watermarks),
                    columns=_adapter_replay_columns(external_config),
                    window=AdapterReplayWindow(
                        lower_bound_mode=_lower_bound_mode(root),
                        lower_bound_inclusive=True,
                        boundary_time=boundary_time,
                        forced_start_time=root.forced_start_time,
                        lookback_seconds=root.execution_lookback_seconds,
                    ),
                    seed_mode=(
                        AdapterReplaySeedMode.HISTORY_PREFIX
                        if root.execution_mode == REBUILD_EXECUTION_MODE_SEEDED_BOUNDED
                        else AdapterReplaySeedMode.NONE
                    ),
                    target_column_names=tuple(column.name for column in root_table.columns),
                ),
            )
        )
    return tuple(requests)


def _root_has_qualifying_replay_input(
    *,
    client: AdapterConnection,
    root: PopulationRoot,
    plan: PopulationPlan,
    desired_state: DesiredState,
    default_database: str,
    watermarks: tuple[PopulationWatermark, ...],
    boundary_time: str,
) -> bool:
    physical_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name for prepared in plan.objects
    }
    database: str = root.root_key.database or default_database
    relation_name: str = physical_name_by_key.get(
        root.upstream_boundary_key, root.upstream_boundary_key.name
    )
    if not _query_has_rows(
        client=client,
        statement=f"SELECT 1 FROM {database}.{relation_name} LIMIT 1",
    ):
        return False
    mode: AdapterReplayBoundaryMode = AdapterReplayBoundaryMode(root.replay_lineage_mode)
    root_watermarks: tuple[PopulationWatermark, ...] = tuple(
        watermark for watermark in watermarks if watermark.root_key == root.root_key
    )
    columns: AdapterReplayColumns = _adapter_replay_columns(
        _external_source_config(desired_state=desired_state, key=root.upstream_boundary_key)
    )
    qualifying_statement: str | None = _qualifying_input_statement(
        mode=mode,
        database=database,
        relation_name=relation_name,
        columns=columns,
        watermarks=root_watermarks,
        boundary_time=boundary_time,
    )
    if qualifying_statement is None or not _query_has_rows(
        client=client, statement=qualifying_statement
    ):
        raise PopulationExecutionError(
            f"Replay root '{root.root_key.name}' retained input "
            f"'{database}.{relation_name}' has rows but no qualifying {mode} cutoff at "
            f"warehouse boundary {boundary_time}"
        )
    return True


def _qualifying_input_statement(
    *,
    mode: AdapterReplayBoundaryMode,
    database: str,
    relation_name: str,
    columns: AdapterReplayColumns,
    watermarks: tuple[PopulationWatermark, ...],
    boundary_time: str,
) -> str | None:
    predicate: str | None = None
    if mode == AdapterReplayBoundaryMode.OFFSETS and watermarks:
        parts: tuple[str, ...] = tuple(
            f"(toString({columns.partition}) = '{watermark.boundary_key.split('=', 1)[1]}' "
            f"AND {columns.offset} <= toInt64('{watermark.cutoff_value}'))"
            for watermark in watermarks
        )
        predicate = " OR ".join(parts)
    elif mode == AdapterReplayBoundaryMode.CURSOR and watermarks and watermarks[0].cutoff_value:
        predicate = f"{columns.cursor} <= toInt64('{watermarks[0].cutoff_value}')"
    elif mode in {AdapterReplayBoundaryMode.TIMESTAMP, AdapterReplayBoundaryMode.LANDED_AT}:
        boundary_column: str = (
            columns.timestamp if mode == AdapterReplayBoundaryMode.TIMESTAMP else columns.landed_at
        )
        predicate = f"{boundary_column} <= CAST('{boundary_time}' AS DateTime64(3, 'UTC'))"
    if predicate is None:
        return None
    return f"SELECT 1 FROM {database}.{relation_name} WHERE {predicate} LIMIT 1"


def _query_has_rows(*, client: AdapterConnection, statement: str) -> bool:
    result: AdapterQueryResult = client.query(statement)
    return bool(result.rows)


def _adapter_boundaries(
    *,
    mode: AdapterReplayBoundaryMode,
    watermarks: tuple[PopulationWatermark, ...],
) -> tuple[AdapterReplayBoundary, ...]:
    if mode == AdapterReplayBoundaryMode.OFFSETS:
        return tuple(
            AdapterReplayBoundary(
                boundary_key=watermark.boundary_key,
                cutoff_value=watermark.cutoff_value,
                cutoff_inclusive=True,
                partition_value=watermark.boundary_key.split("=", 1)[1],
            )
            for watermark in watermarks
        )
    return tuple(
        AdapterReplayBoundary(
            boundary_key=watermark.boundary_key,
            cutoff_value=watermark.cutoff_value,
            cutoff_inclusive=True,
        )
        for watermark in watermarks
    )


def _adapter_replay_columns(
    external_config: ExternalSourceReplayConfig | None,
) -> AdapterReplayColumns:
    if external_config is None:
        return AdapterReplayColumns(
            partition=REPLAY_PARTITION_COLUMN_NAME,
            offset=REPLAY_OFFSET_COLUMN_NAME,
            timestamp=REPLAY_TIMESTAMP_COLUMN_NAME,
            landed_at=REPLAY_LANDED_AT_COLUMN_NAME,
            cursor=REPLAY_CURSOR_COLUMN_NAME,
        )
    return AdapterReplayColumns(
        partition=external_config.partition_column_name or REPLAY_PARTITION_COLUMN_NAME,
        offset=external_config.offset_column_name or REPLAY_OFFSET_COLUMN_NAME,
        timestamp=external_config.timestamp_column_name or REPLAY_TIMESTAMP_COLUMN_NAME,
        landed_at=(
            external_config.landed_at_column_name
            or external_config.timestamp_column_name
            or REPLAY_LANDED_AT_COLUMN_NAME
        ),
        cursor=external_config.cursor_column_name or REPLAY_CURSOR_COLUMN_NAME,
    )


def _lower_bound_mode(root: PopulationRoot) -> AdapterReplayLowerBoundMode:
    if root.forced_start_time is not None:
        return AdapterReplayLowerBoundMode.FORCED_TIME
    if root.execution_lookback_seconds is not None:
        return AdapterReplayLowerBoundMode.LOOKBACK
    if root.execution_mode in {
        REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
        REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
    }:
        return AdapterReplayLowerBoundMode.ACTIVE_FRONTIER
    return AdapterReplayLowerBoundMode.NONE


def _external_source_config(
    *, desired_state: DesiredState, key: ObjectKey
) -> ExternalSourceReplayConfig | None:
    config: ExternalSourceReplayConfig
    for config in desired_state.external_source_replay_configs:
        if config.key == key:
            return config
    return None
