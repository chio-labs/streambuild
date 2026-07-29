"""Persist and enforce the replay coverage required for deterministic standard reruns."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterOwnershipRecord,
    AdapterQueryResult,
    AdapterReplayColumns,
    AdapterReplayCoverageRange,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.compiler.compile.constants import (
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import StandardPlan, StandardReplayRoot
from streambuild.executor.standard.exceptions import StandardBuildError
from streambuild.executor.standard.models import StandardReplayCoverage

_CANONICAL_REPLAY_COLUMNS: AdapterReplayColumns = AdapterReplayColumns(
    partition=REPLAY_PARTITION_COLUMN_NAME,
    offset=REPLAY_OFFSET_COLUMN_NAME,
    timestamp=REPLAY_TIMESTAMP_COLUMN_NAME,
    landed_at=REPLAY_LANDED_AT_COLUMN_NAME,
    cursor=REPLAY_CURSOR_COLUMN_NAME,
)


def resolve_required_replay_coverage(
    *,
    client: AdapterConnection,
    plan: StandardPlan,
    database: str,
    existing_relation_names: frozenset[str],
    existing_ownership: tuple[AdapterOwnershipRecord, ...],
    target_relation_name_by_model_name: dict[str, str],
) -> tuple[StandardReplayCoverage, ...]:
    """Resolve the live or durable lineage ranges that a rerun must preserve."""

    resolved: list[StandardReplayCoverage] = []
    root: StandardReplayRoot
    for root in plan.replay_roots:
        resolved.append(
            StandardReplayCoverage(
                model_name=root.model_key.name,
                driving_input_replay_columns=root.driving_input_replay_columns,
                ranges=_required_root_ranges(
                    client=client,
                    root=root,
                    database=database,
                    existing_relation_names=existing_relation_names,
                    existing_ownership=existing_ownership,
                    target_relation_name=target_relation_name_by_model_name[root.model_key.name],
                    has_aggregate_semantics=root.has_aggregate_semantics,
                ),
            )
        )
    return tuple(resolved)


def assert_preserved_history_covers_ranges(
    *,
    client: AdapterConnection,
    replay_coverage: tuple[StandardReplayCoverage, ...],
    database: str,
) -> None:
    """Refuse a rebuild when retained input no longer spans its required replay ranges."""

    shortfalls: list[str] = []
    coverage: StandardReplayCoverage
    for coverage in replay_coverage:
        shortfalls.extend(_coverage_shortfalls(client=client, coverage=coverage, database=database))
    if shortfalls:
        raise StandardBuildError(
            "Standard rerun would silently drop retained history because the preserved driving "
            f"input no longer covers the required replay range: {'; '.join(shortfalls)}. Restore "
            "the aged-out history, or remove the target and its standard ownership claim "
            "explicitly to accept a shorter rebuild."
        )


def capture_completed_replay_coverage(
    *, client: AdapterConnection, plan: StandardPlan, database: str
) -> tuple[StandardReplayCoverage, ...]:
    """Capture the retained input ranges protected after a completed standard replay."""

    return tuple(
        StandardReplayCoverage(
            model_name=root.model_key.name,
            driving_input_replay_columns=root.driving_input_replay_columns,
            ranges=_relation_ranges(
                client=client,
                model_name=root.model_key.name,
                driving_input_relation_name=root.driving_input_relation_name,
                replay_boundary_mode=ReplayLineageMode(root.replay_boundary_mode),
                database=database,
                relation_name=root.driving_input_relation_name,
                query_columns=root.driving_input_replay_columns,
                source_columns=root.driving_input_replay_columns,
            ),
        )
        for root in plan.replay_roots
    )


def _required_root_ranges(
    *,
    client: AdapterConnection,
    root: StandardReplayRoot,
    database: str,
    existing_relation_names: frozenset[str],
    existing_ownership: tuple[AdapterOwnershipRecord, ...],
    target_relation_name: str,
    has_aggregate_semantics: bool,
) -> tuple[AdapterReplayCoverageRange, ...]:
    live_ranges: tuple[AdapterReplayCoverageRange, ...] = ()
    if target_relation_name in existing_relation_names and not has_aggregate_semantics:
        live_ranges = _relation_ranges(
            client=client,
            model_name=root.model_key.name,
            driving_input_relation_name=root.driving_input_relation_name,
            replay_boundary_mode=ReplayLineageMode(root.replay_boundary_mode),
            database=database,
            relation_name=target_relation_name,
            query_columns=_CANONICAL_REPLAY_COLUMNS,
            source_columns=root.driving_input_replay_columns,
        )
    durable_ranges: tuple[AdapterReplayCoverageRange, ...] = _durable_model_ranges(
        existing_ownership=existing_ownership,
        database=database,
        model_name=root.model_key.name,
        driving_input_relation_name=root.driving_input_relation_name,
        replay_boundary_mode=AdapterReplayBoundaryMode(root.replay_boundary_mode),
        source_columns=root.driving_input_replay_columns,
    )
    if durable_ranges:
        return _required_union(durable_ranges=durable_ranges, live_ranges=live_ranges)
    if live_ranges:
        return live_ranges
    return _relation_ranges(
        client=client,
        model_name=root.model_key.name,
        driving_input_relation_name=root.driving_input_relation_name,
        replay_boundary_mode=ReplayLineageMode(root.replay_boundary_mode),
        database=database,
        relation_name=root.driving_input_relation_name,
        query_columns=root.driving_input_replay_columns,
        source_columns=root.driving_input_replay_columns,
    )


def _coverage_shortfalls(
    *, client: AdapterConnection, coverage: StandardReplayCoverage, database: str
) -> tuple[str, ...]:
    if not coverage.ranges:
        return ()
    first_range: AdapterReplayCoverageRange = coverage.ranges[0]
    available_ranges: tuple[AdapterReplayCoverageRange, ...] = _relation_ranges(
        client=client,
        model_name=coverage.model_name,
        driving_input_relation_name=first_range.driving_input_relation_name,
        replay_boundary_mode=ReplayLineageMode(first_range.replay_boundary_mode),
        database=database,
        relation_name=first_range.driving_input_relation_name,
        query_columns=coverage.driving_input_replay_columns,
        source_columns=coverage.driving_input_replay_columns,
    )
    return tuple(
        _shortfall_message(
            model_name=coverage.model_name,
            required=required,
            available=_ranges_for_key(ranges=available_ranges, boundary_key=required.boundary_key),
        )
        for required in coverage.ranges
        if not _range_is_covered(
            required=required,
            available=_ranges_for_key(ranges=available_ranges, boundary_key=required.boundary_key),
        )
    )


def _durable_model_ranges(
    *,
    existing_ownership: tuple[AdapterOwnershipRecord, ...],
    database: str,
    model_name: str,
    driving_input_relation_name: str,
    replay_boundary_mode: AdapterReplayBoundaryMode,
    source_columns: AdapterReplayColumns,
) -> tuple[AdapterReplayCoverageRange, ...]:
    record: AdapterOwnershipRecord | None = next(
        (
            candidate
            for candidate in existing_ownership
            if candidate.database_name == database
            and candidate.logical_model_name == model_name
            and candidate.replay_coverage
        ),
        None,
    )
    if record is None:
        return ()
    mismatched_ranges: tuple[AdapterReplayCoverageRange, ...] = tuple(
        replay_range
        for replay_range in record.replay_coverage
        if replay_range.driving_input_relation_name != driving_input_relation_name
        or replay_range.replay_boundary_mode != replay_boundary_mode
        or replay_range.source_partition_column_name
        != _source_partition_column(mode=replay_boundary_mode, columns=source_columns)
        or replay_range.source_position_column_name
        != _source_position_column(mode=replay_boundary_mode, columns=source_columns)
        or replay_range.source_timestamp_column_name != source_columns.timestamp
    )
    if mismatched_ranges:
        raise StandardBuildError(
            f"Standard rerun cannot reuse replay coverage for model '{model_name}' because its "
            f"driving input, replay mode, or physical mapping changed. Existing coverage uses "
            f"'{mismatched_ranges[0].driving_input_relation_name}' in "
            f"'{mismatched_ranges[0].replay_boundary_mode}' mode; the current plan uses "
            f"'{driving_input_relation_name}' in '{replay_boundary_mode}' mode. Restore the "
            "previous contract and replay columns, or remove the target and its standard ownership "
            "claim explicitly."
        )
    return record.replay_coverage


def _relation_ranges(
    *,
    client: AdapterConnection,
    model_name: str,
    driving_input_relation_name: str,
    replay_boundary_mode: ReplayLineageMode,
    database: str,
    relation_name: str,
    query_columns: AdapterReplayColumns,
    source_columns: AdapterReplayColumns,
) -> tuple[AdapterReplayCoverageRange, ...]:
    if replay_boundary_mode == ReplayLineageMode.OFFSETS:
        return _offset_ranges(
            client=client,
            driving_input_relation_name=driving_input_relation_name,
            database=database,
            relation_name=relation_name,
            query_columns=query_columns,
            source_columns=source_columns,
        )
    return _scalar_ranges(
        client=client,
        model_name=model_name,
        driving_input_relation_name=driving_input_relation_name,
        mode=replay_boundary_mode,
        database=database,
        relation_name=relation_name,
        query_columns=query_columns,
        source_columns=source_columns,
    )


def _offset_ranges(
    *,
    client: AdapterConnection,
    driving_input_relation_name: str,
    database: str,
    relation_name: str,
    query_columns: AdapterReplayColumns,
    source_columns: AdapterReplayColumns,
) -> tuple[AdapterReplayCoverageRange, ...]:
    result: AdapterQueryResult = client.query(
        f"SELECT {query_columns.partition}, min({query_columns.offset}), "
        f"max({query_columns.offset}) FROM (SELECT {query_columns.partition}, "
        f"{query_columns.offset}, {query_columns.offset} - toInt64(row_number() "
        f"OVER (PARTITION BY {query_columns.partition} ORDER BY {query_columns.offset})) "
        f"AS sequence_group FROM (SELECT DISTINCT {query_columns.partition}, "
        f"{query_columns.offset} FROM {database}.{relation_name})) GROUP BY "
        f"{query_columns.partition}, sequence_group ORDER BY "
        f"{query_columns.partition}, min({query_columns.offset})"
    )
    return tuple(
        AdapterReplayCoverageRange(
            driving_input_relation_name=driving_input_relation_name,
            replay_boundary_mode=AdapterReplayBoundaryMode.OFFSETS,
            boundary_key=f"{REPLAY_PARTITION_COLUMN_NAME}={row[0]}",
            source_partition_column_name=source_columns.partition,
            source_position_column_name=source_columns.offset,
            source_timestamp_column_name=source_columns.timestamp,
            lower_value=str(row[1]),
            upper_value=str(row[2]),
        )
        for row in result.rows
        if row[0] is not None and row[1] is not None and row[2] is not None
    )


def _scalar_ranges(
    *,
    client: AdapterConnection,
    model_name: str,
    driving_input_relation_name: str,
    mode: ReplayLineageMode,
    database: str,
    relation_name: str,
    query_columns: AdapterReplayColumns,
    source_columns: AdapterReplayColumns,
) -> tuple[AdapterReplayCoverageRange, ...]:
    boundary_column: str = _source_position_column(mode=mode, columns=query_columns)
    canonical_boundary_column: str = _source_position_column(
        mode=mode, columns=_CANONICAL_REPLAY_COLUMNS
    )
    result: AdapterQueryResult = client.query(
        f"SELECT min({boundary_column}), max({boundary_column}) FROM "
        f"{database}.{relation_name} HAVING count() > 0"
    )
    if not result.rows or result.rows[0][0] is None or result.rows[0][1] is None:
        return ()
    return (
        AdapterReplayCoverageRange(
            driving_input_relation_name=driving_input_relation_name,
            replay_boundary_mode=AdapterReplayBoundaryMode(mode),
            boundary_key=canonical_boundary_column,
            source_partition_column_name=None,
            source_position_column_name=_source_position_column(mode=mode, columns=source_columns),
            source_timestamp_column_name=source_columns.timestamp,
            lower_value=str(result.rows[0][0]),
            upper_value=str(result.rows[0][1]),
        ),
    )


def _range_is_covered(
    *,
    required: AdapterReplayCoverageRange,
    available: tuple[AdapterReplayCoverageRange, ...],
) -> bool:
    if required.replay_boundary_mode in {
        AdapterReplayBoundaryMode.OFFSETS,
        AdapterReplayBoundaryMode.CURSOR,
    }:
        return any(
            int(candidate.lower_value) <= int(required.lower_value)
            and int(candidate.upper_value) >= int(required.upper_value)
            for candidate in available
        )
    return any(
        candidate.lower_value <= required.lower_value
        and candidate.upper_value >= required.upper_value
        for candidate in available
    )


def _shortfall_message(
    *,
    model_name: str,
    required: AdapterReplayCoverageRange,
    available: tuple[AdapterReplayCoverageRange, ...],
) -> str:
    available_text: str = "no retained rows"
    if available:
        available_text = ", ".join(
            f"{candidate.lower_value}..{candidate.upper_value}" for candidate in available
        )
    return (
        f"{model_name} requires {required.boundary_key} "
        f"{required.lower_value}..{required.upper_value}, but "
        f"{required.driving_input_relation_name} has {available_text}"
    )


def _ranges_for_key(
    *, ranges: tuple[AdapterReplayCoverageRange, ...], boundary_key: str
) -> tuple[AdapterReplayCoverageRange, ...]:
    return tuple(
        replay_range for replay_range in ranges if replay_range.boundary_key == boundary_key
    )


def _required_union(
    *,
    durable_ranges: tuple[AdapterReplayCoverageRange, ...],
    live_ranges: tuple[AdapterReplayCoverageRange, ...],
) -> tuple[AdapterReplayCoverageRange, ...]:
    additions: tuple[AdapterReplayCoverageRange, ...] = tuple(
        live_range
        for live_range in live_ranges
        if not _range_is_covered(
            required=live_range,
            available=_ranges_for_key(ranges=durable_ranges, boundary_key=live_range.boundary_key),
        )
    )
    return (*durable_ranges, *additions)


def _source_partition_column(
    *, mode: AdapterReplayBoundaryMode | ReplayLineageMode, columns: AdapterReplayColumns
) -> str | None:
    if ReplayLineageMode(mode) == ReplayLineageMode.OFFSETS:
        return columns.partition
    return None


def _source_position_column(
    *, mode: AdapterReplayBoundaryMode | ReplayLineageMode, columns: AdapterReplayColumns
) -> str:
    position_column: str | None = {
        ReplayLineageMode.OFFSETS: columns.offset,
        ReplayLineageMode.TIMESTAMP: columns.timestamp,
        ReplayLineageMode.LANDED_AT: columns.landed_at,
        ReplayLineageMode.CURSOR: columns.cursor,
    }.get(ReplayLineageMode(mode))
    if position_column is None:
        raise StandardBuildError(f"Standard build does not support replay boundary mode '{mode}'")
    return position_column
