"""Decode and calculate approximate replay progress from committed offset frontiers."""

from collections.abc import Mapping
from typing import cast

from streambuild.adapter.models import (
    AdapterReplayOffsetFrontier,
    AdapterReplayOffsetProgressRequest,
    AdapterReplayOffsetRange,
)
from streambuild.dev_server.models import ReplayOffsetProgress


def decode_replay_offset_progress_request(
    value: object,
) -> AdapterReplayOffsetProgressRequest | None:
    """Decode persisted event metadata conservatively for historical compatibility."""

    if not isinstance(value, Mapping):
        return None
    metadata: Mapping[str, object] = cast(Mapping[str, object], value)
    raw_ranges: object = metadata.get("ranges")
    if not isinstance(raw_ranges, list):
        return None
    try:
        decoded_ranges: list[AdapterReplayOffsetRange] = []
        for raw_item in raw_ranges:
            if not isinstance(raw_item, Mapping):
                continue
            item: Mapping[str, object] = cast(Mapping[str, object], raw_item)
            decoded_ranges.append(
                AdapterReplayOffsetRange(
                    partition=int(str(item["partition"])),
                    lower_offset=int(str(item["lowerOffset"])),
                    upper_offset=int(str(item["upperOffset"])),
                )
            )
        ranges: tuple[AdapterReplayOffsetRange, ...] = tuple(decoded_ranges)
        database: str = str(metadata["database"])
        relation: str = str(metadata["relation"])
        partition_column: str = str(metadata["partitionColumn"])
        offset_column: str = str(metadata["offsetColumn"])
    except (KeyError, TypeError, ValueError):
        return None
    if not ranges or not all((database, relation, partition_column, offset_column)):
        return None
    return AdapterReplayOffsetProgressRequest(
        database=database,
        relation=relation,
        partition_column=partition_column,
        offset_column=offset_column,
        ranges=ranges,
    )


def calculate_replay_offset_progress(
    *,
    request: AdapterReplayOffsetProgressRequest,
    frontiers: tuple[AdapterReplayOffsetFrontier, ...],
    elapsed_seconds: float,
    completed: bool = False,
) -> ReplayOffsetProgress | None:
    """Weight partition completion by captured offset span and clamp sparse frontiers."""

    spans: tuple[tuple[AdapterReplayOffsetRange, int], ...] = tuple(
        (item, max(item.upper_offset - item.lower_offset, 0)) for item in request.ranges
    )
    total_span: int = sum(span for _item, span in spans)
    if total_span <= 0:
        return None
    frontier_by_partition: dict[int, int] = {}
    for frontier in frontiers:
        frontier_by_partition[frontier.partition] = max(
            frontier.completed_offset,
            frontier_by_partition.get(frontier.partition, frontier.completed_offset),
        )
    completed_span: int = (
        total_span
        if completed
        else sum(
            min(
                max(
                    frontier_by_partition.get(item.partition, item.lower_offset)
                    - item.lower_offset,
                    0,
                ),
                span,
            )
            for item, span in spans
        )
    )
    percentage: float = min(max(completed_span / total_span * 100, 0.0), 100.0)
    velocity: float = 0.0 if elapsed_seconds <= 0 else completed_span / elapsed_seconds
    eta_seconds: float | None = (
        0.0
        if completed
        else None
        if velocity <= 0
        else max((total_span - completed_span) / velocity, 0.0)
    )
    return ReplayOffsetProgress(
        percentage=percentage,
        eta_seconds=eta_seconds,
        completed_span=completed_span,
        total_span=total_span,
        observed_partitions=len(
            frontier_by_partition.keys() & {item.partition for item, _span in spans}
        ),
        total_partitions=len({item.partition for item, _span in spans}),
    )
