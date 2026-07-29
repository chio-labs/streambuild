"""Build and execute replay requests for shared population."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterPhysicalRelationMapping,
    AdapterReplayBoundary,
    AdapterReplayColumns,
    AdapterReplayQuery,
    AdapterReplayRelations,
    AdapterReplayRequest,
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
from streambuild.executor.population.models import (
    PopulationPlan,
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
) -> tuple[ObjectKey, ...]:
    """Execute every populated root through one request builder."""

    requests: tuple[tuple[ObjectKey, AdapterReplayRequest], ...] = _build_replay_requests(
        plan=plan,
        desired_state=desired_state,
        default_database=default_database,
        watermarks=watermarks,
        boundary_time=boundary_time,
    )
    request: AdapterReplayRequest
    for _root_key, request in requests:
        client.execute_replay(request)
    return tuple(root_key for root_key, _request in requests)


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
