"""Read-only SQL builders for the live warehouse overlay."""

from __future__ import annotations

from streambuild.dev_server.constants import THROUGHPUT_WINDOW_LADDER


def build_relation_stats_query(*, database: str) -> str:
    """Approximate rows and bytes for every relation in one scan of system.tables."""

    return (
        "SELECT name, coalesce(total_rows, 0) AS total_rows, "
        "coalesce(total_bytes, 0) AS total_bytes "
        f"FROM system.tables WHERE database = '{database}'"
    )


def build_parts_query(*, database: str) -> str:
    """Active part counts per relation in one scan of system.parts."""

    return (
        "SELECT table, count() AS parts "
        f"FROM system.parts WHERE database = '{database}' AND active GROUP BY table"
    )


def build_extents_query(*, database: str, relation_names: tuple[str, ...]) -> str:
    """Oldest and newest landed event per lineage-bearing relation, batched."""

    selects: list[str] = [
        (
            f"SELECT '{name}' AS relation, "
            "toString(min(_replay_landed_at)) AS oldest, "
            "toString(max(_replay_landed_at)) AS newest, "
            "count() AS rows "
            f"FROM `{database}`.`{name}` HAVING count() > 0"
        )
        for name in relation_names
    ]
    return " UNION ALL ".join(selects)


def build_throughput_query(
    *,
    database: str,
    relation_name: str,
    window_seconds: int,
    bucket_seconds: int,
) -> str:
    """Landed-event counts per bucket over one window of a lineage-bearing relation."""

    return (
        "SELECT toUnixTimestamp(toStartOfInterval("
        f"_replay_landed_at, INTERVAL {bucket_seconds} SECOND)) AS bucket, "
        "count() AS rows "
        f"FROM `{database}`.`{relation_name}` "
        f"WHERE _replay_landed_at >= now64(3) - INTERVAL {window_seconds} SECOND "
        "GROUP BY bucket ORDER BY bucket"
    )


def build_partitions_query(*, database: str, relation_name: str) -> str:
    """Per-partition landed offsets for one managed raw relation."""

    return (
        "SELECT _replay_partition AS partition, "
        "max(_replay_offset) AS max_offset, "
        "toString(max(_replay_landed_at)) AS newest "
        f"FROM `{database}`.`{relation_name}` GROUP BY partition ORDER BY partition"
    )


def choose_throughput_window(*, newest_age_seconds: float | None) -> tuple[int, int]:
    """Pick the smallest ladder rung whose window still contains the newest event."""

    if newest_age_seconds is None:
        return THROUGHPUT_WINDOW_LADDER[-1]
    for window_seconds, bucket_seconds in THROUGHPUT_WINDOW_LADDER:
        if newest_age_seconds < window_seconds:
            return (window_seconds, bucket_seconds)
    return THROUGHPUT_WINDOW_LADDER[-1]
