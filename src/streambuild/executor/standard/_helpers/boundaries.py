"""Capture the one inclusive/exclusive boundary separating replay from live rows."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterQueryResult
from streambuild.compiler.compile.constants import (
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import StandardPlan, StandardReplayRoot
from streambuild.executor.standard.constants import SCALAR_BOUNDARY_COLUMN_BY_MODE
from streambuild.executor.standard.exceptions import StandardBuildError
from streambuild.executor.standard.models import StandardReplayBoundary


def capture_replay_boundaries(
    *,
    client: AdapterConnection,
    plan: StandardPlan,
    database: str,
    boundary_time: str,
    target_relation_name_by_model_name: dict[str, str],
) -> tuple[StandardReplayBoundary, ...]:
    """Capture one boundary per replay root from live and preserved warehouse evidence."""

    boundaries: list[StandardReplayBoundary] = []
    root: StandardReplayRoot
    for root in plan.replay_roots:
        boundaries.extend(
            _root_boundaries(
                client=client,
                root=root,
                database=database,
                boundary_time=boundary_time,
                target_relation_name=target_relation_name_by_model_name[root.model_key.name],
            )
        )
    return tuple(boundaries)


def _root_boundaries(
    *,
    client: AdapterConnection,
    root: StandardReplayRoot,
    database: str,
    boundary_time: str,
    target_relation_name: str,
) -> tuple[StandardReplayBoundary, ...]:
    mode: ReplayLineageMode = ReplayLineageMode(root.replay_boundary_mode)
    if mode == ReplayLineageMode.OFFSETS:
        return _offset_boundaries(
            client=client,
            root=root,
            database=database,
            boundary_time=boundary_time,
            target_relation_name=target_relation_name,
        )
    return _scalar_boundaries(
        client=client,
        root=root,
        mode=mode,
        database=database,
        boundary_time=boundary_time,
        target_relation_name=target_relation_name,
    )


def _offset_boundaries(
    *,
    client: AdapterConnection,
    root: StandardReplayRoot,
    database: str,
    boundary_time: str,
    target_relation_name: str,
) -> tuple[StandardReplayBoundary, ...]:
    live_floor_by_partition: dict[str, str] = _partition_values(
        result=client.query(
            f"SELECT {REPLAY_PARTITION_COLUMN_NAME}, min({REPLAY_OFFSET_COLUMN_NAME}) "
            f"FROM {database}.{target_relation_name} GROUP BY {REPLAY_PARTITION_COLUMN_NAME}"
        )
    )
    preserved_cutoff_by_partition: dict[str, str] = _partition_values(
        result=client.query(
            f"SELECT {REPLAY_PARTITION_COLUMN_NAME}, max({REPLAY_OFFSET_COLUMN_NAME}) "
            f"FROM {database}.{root.driving_input_relation_name} "
            f"WHERE {REPLAY_LANDED_AT_COLUMN_NAME} <= CAST('{boundary_time}' AS DateTime64(3)) "
            f"GROUP BY {REPLAY_PARTITION_COLUMN_NAME}"
        )
    )
    return tuple(
        _boundary(
            root=root,
            boundary_key=f"{REPLAY_PARTITION_COLUMN_NAME}={partition_value}",
            live_floor=live_floor_by_partition.get(partition_value),
            preserved_cutoff=preserved_cutoff_by_partition[partition_value],
        )
        for partition_value in sorted(preserved_cutoff_by_partition)
    )


def _scalar_boundaries(
    *,
    client: AdapterConnection,
    root: StandardReplayRoot,
    mode: ReplayLineageMode,
    database: str,
    boundary_time: str,
    target_relation_name: str,
) -> tuple[StandardReplayBoundary, ...]:
    boundary_column: str | None = SCALAR_BOUNDARY_COLUMN_BY_MODE.get(mode)
    if boundary_column is None:
        raise StandardBuildError(
            f"Standard build does not support replay boundary mode '{mode}' for "
            f"model '{root.model_key.name}'"
        )
    live_floor: str | None = _scalar_value(
        result=client.query(
            f"SELECT min({boundary_column}) FROM {database}.{target_relation_name} "
            "HAVING count() > 0"
        )
    )
    return (
        _boundary(
            root=root,
            boundary_key=boundary_column,
            live_floor=live_floor,
            preserved_cutoff=boundary_time,
        ),
    )


def _boundary(
    *,
    root: StandardReplayRoot,
    boundary_key: str,
    live_floor: str | None,
    preserved_cutoff: str,
) -> StandardReplayBoundary:
    return StandardReplayBoundary(
        model_name=root.model_key.name,
        driving_input_relation_name=root.driving_input_relation_name,
        replay_boundary_mode=root.replay_boundary_mode,
        boundary_key=boundary_key,
        cutoff_value=preserved_cutoff if live_floor is None else live_floor,
        cutoff_inclusive=live_floor is None,
    )


def _partition_values(*, result: AdapterQueryResult) -> dict[str, str]:
    return {
        str(row[0]): str(row[1]) for row in result.rows if row[0] is not None and row[1] is not None
    }


def _scalar_value(*, result: AdapterQueryResult) -> str | None:
    if not result.rows or result.rows[0][0] is None:
        return None
    return str(result.rows[0][0])
