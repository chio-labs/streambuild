"""Build and execute neutral replay requests for directly named standard relations."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterPhysicalRelationMapping,
    AdapterReplayBoundary,
    AdapterReplayColumns,
    AdapterReplayQuery,
    AdapterReplayRelations,
    AdapterReplayRequest,
    AdapterReplayWindow,
    AdapterTable,
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
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.main.build_adapter_replay_query import (
    build_adapter_replay_query,
)
from streambuild.compiler.planner.models import (
    StandardPlan,
    StandardPopulationSegment,
    StandardReplayRoot,
)
from streambuild.executor.standard.exceptions import StandardBuildError
from streambuild.executor.standard.models import StandardReplayBoundary

_STANDARD_REPLAY_COLUMNS: AdapterReplayColumns = AdapterReplayColumns(
    partition=REPLAY_PARTITION_COLUMN_NAME,
    offset=REPLAY_OFFSET_COLUMN_NAME,
    timestamp=REPLAY_TIMESTAMP_COLUMN_NAME,
    landed_at=REPLAY_LANDED_AT_COLUMN_NAME,
    cursor=REPLAY_CURSOR_COLUMN_NAME,
)


def execute_standard_replay(
    *,
    client: AdapterConnection,
    plan: StandardPlan,
    realized_project: RealizedProject,
    database: str,
    boundary_time: str,
    boundaries: tuple[StandardReplayBoundary, ...],
) -> tuple[str, ...]:
    """Replay each replay root's preserved history below its captured boundary."""

    replayed: list[str] = []
    root: StandardReplayRoot
    for root in plan.replay_roots:
        root_boundaries: tuple[StandardReplayBoundary, ...] = tuple(
            boundary for boundary in boundaries if boundary.model_name == root.model_key.name
        )
        replayed.extend(
            _execute_root_replay(
                client=client,
                root=root,
                realized_project=realized_project,
                database=database,
                boundary_time=boundary_time,
                root_boundaries=root_boundaries,
            )
        )
    return tuple(replayed)


def execute_standard_population_segment(
    *,
    client: AdapterConnection,
    segment: StandardPopulationSegment,
    realized_project: RealizedProject,
    database: str,
    boundary_time: str,
    boundaries: tuple[StandardReplayBoundary, ...],
) -> str:
    """Populate one attached model exactly once from its completed driving input."""

    if boundaries:
        client.execute_replay(
            _build_replay_request(
                root=segment,
                realized_project=realized_project,
                database=database,
                boundary_time=boundary_time,
                root_boundaries=boundaries,
            )
        )
    return segment.model_key.name


def _execute_root_replay(
    *,
    client: AdapterConnection,
    root: StandardReplayRoot,
    realized_project: RealizedProject,
    database: str,
    boundary_time: str,
    root_boundaries: tuple[StandardReplayBoundary, ...],
) -> tuple[str, ...]:
    if not root_boundaries:
        return ()
    client.execute_replay(
        _build_replay_request(
            root=root,
            realized_project=realized_project,
            database=database,
            boundary_time=boundary_time,
            root_boundaries=root_boundaries,
        )
    )
    return (root.model_key.name,)


def _build_replay_request(
    *,
    root: StandardReplayRoot | StandardPopulationSegment,
    realized_project: RealizedProject,
    database: str,
    boundary_time: str,
    root_boundaries: tuple[StandardReplayBoundary, ...],
) -> AdapterReplayRequest:
    table: AdapterTable = _model_table(realized_project=realized_project, key=root.model_key)
    view: AdapterMaterializedView = _model_view(
        realized_project=realized_project, key=root.model_key
    )
    mode: AdapterReplayBoundaryMode = AdapterReplayBoundaryMode(root.replay_boundary_mode)
    return AdapterReplayRequest(
        mode=mode,
        database=database,
        relations=AdapterReplayRelations(
            root=table.name,
            source=view.source_relation_name,
            anchor=root.driving_input_relation_name,
            target=table.name,
        ),
        replay_query=_replay_query(
            view=view,
            realized_project=realized_project,
            database=database,
        ),
        boundaries=_adapter_boundaries(mode=mode, root_boundaries=root_boundaries),
        columns=_STANDARD_REPLAY_COLUMNS,
        window=AdapterReplayWindow(
            lower_bound_mode=AdapterReplayLowerBoundMode.NONE,
            lower_bound_inclusive=True,
            boundary_time=boundary_time,
            forced_start_time=None,
            lookback_seconds=None,
        ),
        seed_mode=AdapterReplaySeedMode.NONE,
        target_column_names=tuple(column.name for column in table.columns),
    )


def _replay_query(
    *,
    view: AdapterMaterializedView,
    realized_project: RealizedProject,
    database: str,
) -> AdapterReplayQuery:
    return build_adapter_replay_query(
        query=view.query,
        source_relation_name=view.source_relation_name,
        database=database,
        physical_relation_mappings=_identity_relation_mappings(realized_project=realized_project),
    )


def _identity_relation_mappings(
    *, realized_project: RealizedProject
) -> tuple[AdapterPhysicalRelationMapping, ...]:
    return tuple(
        AdapterPhysicalRelationMapping(logical_name=relation_name, physical_name=relation_name)
        for relation_name in sorted(set(realized_project.relation_name_by_logical_key.values()))
    )


def _adapter_boundaries(
    *,
    mode: AdapterReplayBoundaryMode,
    root_boundaries: tuple[StandardReplayBoundary, ...],
) -> tuple[AdapterReplayBoundary, ...]:
    if mode == AdapterReplayBoundaryMode.OFFSETS:
        return tuple(
            AdapterReplayBoundary(
                boundary_key=boundary.boundary_key,
                cutoff_value=boundary.cutoff_value,
                cutoff_inclusive=boundary.cutoff_inclusive,
                partition_value=boundary.boundary_key.split("=", 1)[1],
            )
            for boundary in root_boundaries
        )
    return tuple(
        AdapterReplayBoundary(
            boundary_key=boundary.boundary_key,
            cutoff_value=boundary.cutoff_value,
            cutoff_inclusive=boundary.cutoff_inclusive,
        )
        for boundary in root_boundaries
    )


def _model_table(*, realized_project: RealizedProject, key: LogicalResourceKey) -> AdapterTable:
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
    for resource in realized_project.resources_by_logical_key[key]:
        if isinstance(resource, AdapterTable):
            return resource
    raise StandardBuildError(f"Standard replay cannot find the target table of '{key.name}'")


def _model_view(
    *, realized_project: RealizedProject, key: LogicalResourceKey
) -> AdapterMaterializedView:
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
    for resource in realized_project.resources_by_logical_key[key]:
        if isinstance(resource, AdapterMaterializedView):
            return resource
    raise StandardBuildError(f"Standard replay cannot find the materialized view of '{key.name}'")
