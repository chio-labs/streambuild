from __future__ import annotations

from dataclasses import replace

from streambuild.clickhouse.inspect.main.inspect_managed_table_state import (
    inspect_managed_table_state,
)
from streambuild.clickhouse.inspect.models import InspectedActiveTableBinding
from streambuild.compiler.compile.constants import (
    REPLAY_REQUIRED_COLUMN_NAMES_BY_MODE,
)
from streambuild.compiler.compile.models import DesiredState, DesiredTable
from streambuild.compiler.planner.constants import (
    REBUILD_EXECUTION_MODE_FULL,
    REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
)
from streambuild.compiler.planner.models import RebuildSubtree
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseQueryResult
from streambuild.spec.types import BoundedReplayFallback, ReplayLineageMode


def _resolve_subtree_behavior(
    *,
    client: ClickHouseClient,
    subtree: RebuildSubtree,
    desired_state: DesiredState,
    default_database: str,
    replay_lineage_mode: ReplayLineageMode,
) -> RebuildSubtree:
    if subtree.execution_mode != REBUILD_EXECUTION_MODE_SEEDED_BOUNDED:
        return subtree

    root_table: DesiredTable | None = next(
        (
            object_
            for object_ in desired_state.objects
            if isinstance(object_, DesiredTable) and object_.key == subtree.root_key
        ),
        None,
    )
    if root_table is None:
        return subtree
    database: str = root_table.key.database or default_database
    active_table_name: str | None = _active_table_name_for_logical_root(
        client=client,
        database=database,
        logical_table_name=root_table.name,
    )
    if active_table_name is None and subtree.forced_start_time is not None:
        return replace(
            subtree,
            execution_mode=REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
            history_preserving_bounded_supported=False,
            resolved_bounded_replay_fallback=root_table.bounded_replay_fallback,
        )
    if _history_preserving_bounded_supported(
        client=client,
        root_table=root_table,
        default_database=default_database,
        replay_lineage_mode=replay_lineage_mode,
    ):
        return subtree

    return resolve_subtree_behavior_from_support(
        subtree=subtree,
        bounded_replay_fallback=root_table.bounded_replay_fallback,
        history_preserving_bounded_supported=False,
    )


def resolve_subtree_behavior_from_support(
    *,
    subtree: RebuildSubtree,
    bounded_replay_fallback: BoundedReplayFallback | str,
    history_preserving_bounded_supported: bool,
) -> RebuildSubtree:
    resolved_bounded_replay_fallback: BoundedReplayFallback = BoundedReplayFallback(
        bounded_replay_fallback
    )
    if history_preserving_bounded_supported:
        return subtree

    if resolved_bounded_replay_fallback == BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY:
        return replace(
            subtree,
            execution_mode=REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
            history_preserving_bounded_supported=False,
            resolved_bounded_replay_fallback=resolved_bounded_replay_fallback,
        )
    return replace(
        subtree,
        execution_mode=REBUILD_EXECUTION_MODE_FULL,
        requested_start_time=subtree.forced_start_time,
        forced_start_time=None,
        execution_lookback_seconds=None,
        history_preserving_bounded_supported=False,
        resolved_bounded_replay_fallback=resolved_bounded_replay_fallback,
    )


def _history_preserving_bounded_supported(
    *,
    client: ClickHouseClient,
    root_table: DesiredTable,
    default_database: str,
    replay_lineage_mode: ReplayLineageMode,
) -> bool:
    required_column_names: set[str] = _required_history_preserving_column_names(replay_lineage_mode)
    if not required_column_names:
        return True
    database: str = root_table.key.database or default_database
    active_table_name: str | None = _active_table_name_for_logical_root(
        client=client,
        database=database,
        logical_table_name=root_table.name,
    )
    if active_table_name is None:
        return False
    live_column_names: set[str] = _live_column_names(
        client=client,
        database=database,
        live_table_name=active_table_name,
    )
    return required_column_names.issubset(live_column_names)


def _required_history_preserving_column_names(
    replay_lineage_mode: ReplayLineageMode,
) -> set[str]:
    return set(REPLAY_REQUIRED_COLUMN_NAMES_BY_MODE.get(str(replay_lineage_mode), ()))


def _active_table_name_for_logical_root(
    *, client: ClickHouseClient, database: str, logical_table_name: str
) -> str | None:
    active_bindings: tuple[InspectedActiveTableBinding, ...] = inspect_managed_table_state(
        client=client,
        database=database,
    ).active_bindings
    binding: InspectedActiveTableBinding
    for binding in active_bindings:
        if binding.logical_name == logical_table_name:
            return binding.physical_name
    return None


def _live_column_names(
    *,
    client: ClickHouseClient,
    database: str,
    live_table_name: str,
) -> set[str]:
    try:
        result: ClickHouseQueryResult = client.query(f"DESCRIBE TABLE {database}.{live_table_name}")
    except Exception:
        return set()
    rows: tuple[tuple[object, ...], ...] = result.rows
    return {str(row[0]) for row in rows}
