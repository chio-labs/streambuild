"""Compare staged and active relations for ClickHouse readiness."""

from collections.abc import Mapping
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterRelationNotFoundError, AdapterResultError
from streambuild.adapter.models import (
    AdapterReadinessOffsetSummary,
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    AdapterReadinessRootRequest,
    AdapterReadinessScalarSummary,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.adapters.clickhouse._helpers.catalog_parsing import extract_create_query_source
from streambuild.adapters.clickhouse.models import (
    ClickHouseReadinessColumnRow,
    ClickHouseReadinessCountRow,
    ClickHouseReadinessCreateQueryRow,
    ClickHouseReadinessOffsetRow,
    ClickHouseReadinessScalarRow,
)
from streambuild.compiler.compile.constants import (
    MATERIALIZED_VIEW_NAME_PREFIX,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.planner.constants import BLANK_VALUES


def compare_clickhouse_readiness(
    *, connection: AdapterConnection, request: AdapterReadinessRequest
) -> tuple[AdapterReadinessRootObservation, ...]:
    """Return ClickHouse observations for every requested staged root."""

    return tuple(
        _compare_root(connection=connection, root_request=root_request)
        for root_request in request.roots
    )


def _compare_root(
    *, connection: AdapterConnection, root_request: AdapterReadinessRootRequest
) -> AdapterReadinessRootObservation:
    staged_exists: bool = _table_exists(
        connection=connection,
        database=root_request.database,
        table_name=root_request.staged_relation_name,
    )
    active_row_count: int | None = (
        _safe_row_count(
            connection=connection,
            database=root_request.database,
            table_name=root_request.logical_name,
        )
        if root_request.active_exists
        else None
    )
    staged_row_count: int | None = (
        _safe_row_count(
            connection=connection,
            database=root_request.database,
            table_name=root_request.staged_relation_name,
        )
        if staged_exists
        else None
    )
    boundary_mode: AdapterReplayBoundaryMode | None = _infer_replay_boundary_mode(
        connection=connection,
        database=root_request.database,
        table_name=root_request.staged_relation_name,
    )
    staged_materialized_view_name: str = _staged_materialized_view_name(
        root_request.staged_relation_name
    )
    replay_source_name: str | None = (
        _resolve_staged_source_relation(
            connection=connection,
            database=root_request.database,
            staged_materialized_view_name=staged_materialized_view_name,
        )
        if staged_exists
        else None
    )
    replay_source_row_count: int | None = (
        _safe_row_count(
            connection=connection,
            database=root_request.database,
            table_name=replay_source_name,
        )
        if replay_source_name is not None
        else None
    )
    active_queryable: bool = root_request.active_exists and active_row_count is not None
    offset_summary: AdapterReadinessOffsetSummary | None = None
    scalar_summary: AdapterReadinessScalarSummary | None = None
    if staged_exists and boundary_mode == AdapterReplayBoundaryMode.OFFSETS:
        offset_summary = _offset_summary(
            connection=connection,
            root_request=root_request,
            staged_materialized_view_name=staged_materialized_view_name,
            active_queryable=active_queryable,
        )
    elif active_queryable and staged_exists and boundary_mode is not None:
        scalar_summary = _scalar_summary(
            connection=connection,
            root_request=root_request,
            boundary_mode=boundary_mode,
        )
    return AdapterReadinessRootObservation(
        root=root_request,
        staged_exists=staged_exists,
        active_row_count=active_row_count,
        staged_row_count=staged_row_count,
        replay_source_name=replay_source_name,
        replay_source_row_count=replay_source_row_count,
        replay_boundary_mode=boundary_mode,
        offset_summary=offset_summary,
        scalar_summary=scalar_summary,
    )


def _table_exists(*, connection: AdapterConnection, database: str, table_name: str) -> bool:
    row: ClickHouseReadinessCountRow | None = connection.query_one(
        statement="SELECT count() AS value FROM system.tables "
        f"WHERE database = '{database}' AND name = '{table_name}'",
        decode=_decode_count_row,
    )
    return bool(row.value) if row is not None else False


def _safe_row_count(*, connection: AdapterConnection, database: str, table_name: str) -> int | None:
    if not _table_exists(connection=connection, database=database, table_name=table_name):
        return None
    try:
        row: ClickHouseReadinessCountRow | None = connection.query_one(
            statement=f"SELECT count() AS value FROM {database}.{table_name}",
            decode=_decode_count_row,
        )
    except AdapterRelationNotFoundError:
        return None
    if row is None:
        raise AdapterResultError(f"Expected row count for {database}.{table_name}")
    return row.value


def _infer_replay_boundary_mode(
    *, connection: AdapterConnection, database: str, table_name: str
) -> AdapterReplayBoundaryMode | None:
    rows: tuple[ClickHouseReadinessColumnRow, ...] = connection.query_many(
        statement=(
            f"SELECT name FROM system.columns "
            f"WHERE database = '{database}' AND table = '{table_name}'"
        ),
        decode=_decode_column_row,
    )
    column_names: set[str] = {row.name for row in rows}
    if {REPLAY_PARTITION_COLUMN_NAME, REPLAY_OFFSET_COLUMN_NAME}.issubset(column_names):
        return AdapterReplayBoundaryMode.OFFSETS
    if REPLAY_TIMESTAMP_COLUMN_NAME in column_names:
        return AdapterReplayBoundaryMode.TIMESTAMP
    if REPLAY_LANDED_AT_COLUMN_NAME in column_names:
        return AdapterReplayBoundaryMode.LANDED_AT
    return None


def _offset_summary(
    *,
    connection: AdapterConnection,
    root_request: AdapterReadinessRootRequest,
    staged_materialized_view_name: str,
    active_queryable: bool,
) -> AdapterReadinessOffsetSummary:
    active_offsets_sql: str = _active_offsets_sql(
        root_request=root_request,
        active_queryable=active_queryable,
    )
    staged_offsets_sql: str = (
        f"SELECT {REPLAY_PARTITION_COLUMN_NAME}, max({REPLAY_OFFSET_COLUMN_NAME}) AS max_offset "
        f"FROM {root_request.database}.{root_request.staged_relation_name} "
        f"GROUP BY {REPLAY_PARTITION_COLUMN_NAME}"
    )
    source_relation_name: str | None = _resolve_staged_source_relation(
        connection=connection,
        database=root_request.database,
        staged_materialized_view_name=staged_materialized_view_name,
    )
    boundary_column: str | None = (
        None
        if source_relation_name is None
        else _resolve_offset_boundary_column(
            connection=connection,
            database=root_request.database,
            source_relation_name=source_relation_name,
        )
    )
    raw_offsets_sql: str | None = _raw_offsets_sql(
        database=root_request.database,
        source_relation_name=source_relation_name,
    )
    staged_progress_sql: str | None = _staged_progress_sql(
        database=root_request.database,
        source_relation_name=source_relation_name,
        boundary_column=boundary_column,
        staged_offsets_sql=staged_offsets_sql,
    )
    row: ClickHouseReadinessOffsetRow | None = connection.query_one(
        statement=_offset_summary_query(
            active_offsets_sql=active_offsets_sql,
            staged_offsets_sql=staged_offsets_sql,
            raw_offsets_sql=raw_offsets_sql,
            staged_progress_sql=staged_progress_sql,
            database=root_request.database,
            source_relation_name=source_relation_name,
            boundary_column=boundary_column,
        ),
        decode=_decode_offset_row,
    )
    if row is None:
        raise AdapterResultError("Expected offset catchup summary row")
    return AdapterReadinessOffsetSummary(
        active_partition_count=row.active_partition_count,
        staged_partition_count=row.staged_partition_count,
        partitions_compared=row.partitions_compared,
        missing_staged_partition_count=row.missing_staged_partition_count,
        missing_freshness_partition_count=row.missing_freshness_partition_count,
        lagging_partition_count=row.lagging_partition_count,
        max_offset_gap=row.max_offset_gap,
        average_offset_gap=row.average_offset_gap,
        lag_boundary_column=boundary_column,
        max_lag_seconds=row.max_lag_seconds,
        average_lag_seconds=row.average_lag_seconds,
    )


def _active_offsets_sql(
    *, root_request: AdapterReadinessRootRequest, active_queryable: bool
) -> str:
    if not active_queryable:
        return (
            f"SELECT toInt64(0) AS {REPLAY_PARTITION_COLUMN_NAME}, toInt64(0) AS max_offset WHERE 0"
        )
    return (
        f"SELECT {REPLAY_PARTITION_COLUMN_NAME}, "
        f"max({REPLAY_OFFSET_COLUMN_NAME}) AS max_offset "
        f"FROM {root_request.database}.{root_request.logical_name} "
        f"GROUP BY {REPLAY_PARTITION_COLUMN_NAME}"
    )


def _raw_offsets_sql(*, database: str, source_relation_name: str | None) -> str | None:
    if source_relation_name is None:
        return None
    return (
        f"SELECT {REPLAY_PARTITION_COLUMN_NAME}, "
        f"max({REPLAY_OFFSET_COLUMN_NAME}) AS max_offset "
        f"FROM {database}.{source_relation_name} GROUP BY {REPLAY_PARTITION_COLUMN_NAME}"
    )


def _staged_progress_sql(
    *,
    database: str,
    source_relation_name: str | None,
    boundary_column: str | None,
    staged_offsets_sql: str,
) -> str | None:
    if source_relation_name is None or boundary_column is None:
        return None
    return (
        f"SELECT source.{REPLAY_PARTITION_COLUMN_NAME}, "
        f"max(source.{boundary_column}) AS staged_max_boundary "
        f"FROM {database}.{source_relation_name} AS source "
        f"INNER JOIN ({staged_offsets_sql}) AS staged_offsets "
        f"ON source.{REPLAY_PARTITION_COLUMN_NAME} = "
        f"staged_offsets.{REPLAY_PARTITION_COLUMN_NAME} "
        f"AND source.{REPLAY_OFFSET_COLUMN_NAME} = staged_offsets.max_offset "
        f"GROUP BY source.{REPLAY_PARTITION_COLUMN_NAME}"
    )


def _scalar_summary(
    *,
    connection: AdapterConnection,
    root_request: AdapterReadinessRootRequest,
    boundary_mode: AdapterReplayBoundaryMode,
) -> AdapterReadinessScalarSummary:
    boundary_column: str = {
        AdapterReplayBoundaryMode.TIMESTAMP: REPLAY_TIMESTAMP_COLUMN_NAME,
        AdapterReplayBoundaryMode.LANDED_AT: REPLAY_LANDED_AT_COLUMN_NAME,
    }[boundary_mode]
    row: ClickHouseReadinessScalarRow | None = connection.query_one(
        statement=(
            "SELECT "
            f"toString(min(active.{boundary_column})) AS active_min_value, "
            f"toString(max(active.{boundary_column})) AS active_max_value, "
            f"toString(min(staged.{boundary_column})) AS staged_min_value, "
            f"toString(max(staged.{boundary_column})) AS staged_max_value, "
            f"dateDiff('second', max(staged.{boundary_column}), "
            f"max(active.{boundary_column})) AS lag_seconds "
            f"FROM {root_request.database}.{root_request.logical_name} AS active "
            f"CROSS JOIN {root_request.database}.{root_request.staged_relation_name} AS staged"
        ),
        decode=_decode_scalar_row,
    )
    if row is None:
        raise AdapterResultError("Expected scalar catchup summary row")
    return AdapterReadinessScalarSummary(
        active_min_value=row.active_min_value,
        active_max_value=row.active_max_value,
        staged_min_value=row.staged_min_value,
        staged_max_value=row.staged_max_value,
        lag_seconds=row.lag_seconds,
    )


def _staged_materialized_view_name(staged_relation_name: str) -> str:
    if not staged_relation_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
        return staged_relation_name
    return MATERIALIZED_VIEW_NAME_PREFIX + staged_relation_name.removeprefix(
        TRANSFORM_TABLE_NAME_PREFIX
    )


def _resolve_staged_source_relation(
    *, connection: AdapterConnection, database: str, staged_materialized_view_name: str
) -> str | None:
    row: ClickHouseReadinessCreateQueryRow | None = connection.query_one(
        statement="SELECT create_table_query FROM system.tables "
        f"WHERE database = '{database}' AND name = '{staged_materialized_view_name}'",
        decode=_decode_create_query_row,
    )
    if row is None:
        return None
    return extract_create_query_source(row.create_table_query)


def _resolve_offset_boundary_column(
    *, connection: AdapterConnection, database: str, source_relation_name: str
) -> str | None:
    rows: tuple[ClickHouseReadinessColumnRow, ...] = connection.query_many(
        statement="SELECT name FROM system.columns "
        f"WHERE database = '{database}' AND table = '{source_relation_name}'",
        decode=_decode_column_row,
    )
    column_names: set[str] = {row.name for row in rows}
    if REPLAY_TIMESTAMP_COLUMN_NAME in column_names:
        return REPLAY_TIMESTAMP_COLUMN_NAME
    if REPLAY_LANDED_AT_COLUMN_NAME in column_names:
        return REPLAY_LANDED_AT_COLUMN_NAME
    return None


def _offset_summary_query(
    *,
    active_offsets_sql: str,
    staged_offsets_sql: str,
    raw_offsets_sql: str | None,
    staged_progress_sql: str | None,
    database: str,
    source_relation_name: str | None,
    boundary_column: str | None,
) -> str:
    raw_offsets_cte: str = _raw_offsets_cte(raw_offsets_sql)
    raw_latest_cte: str = _raw_latest_cte(
        database=database,
        source_relation_name=source_relation_name,
        boundary_column=boundary_column,
    )
    staged_progress_cte: str = _staged_progress_cte(staged_progress_sql)
    return (
        f"WITH active_offsets AS ({active_offsets_sql}), "
        f"staged_offsets AS ({staged_offsets_sql}), "
        f"{raw_offsets_cte}{raw_latest_cte}{staged_progress_cte}"
        "SELECT "
        "(SELECT count() FROM active_offsets) AS active_partition_count, "
        "(SELECT count() FROM staged_offsets) AS staged_partition_count, "
        "countIf(active_offsets.max_offset IS NOT NULL AND "
        "staged_offsets.max_offset IS NOT NULL) AS partitions_compared, "
        "countIf(active_offsets.max_offset IS NOT NULL AND "
        "staged_offsets.max_offset IS NULL) AS missing_staged_partition_count, "
        "countIf(staged_offsets.max_offset IS NOT NULL AND "
        "(staged_progress.staged_max_boundary IS NULL OR "
        "raw_latest.raw_max_boundary IS NULL)) AS missing_freshness_partition_count, "
        "countIf(raw_offsets.max_offset > coalesce(staged_offsets.max_offset, -1)) "
        "AS lagging_partition_count, "
        "max(greatest(raw_offsets.max_offset - "
        "coalesce(staged_offsets.max_offset, raw_offsets.max_offset), 0)) "
        "AS max_offset_gap, "
        "avg(greatest(raw_offsets.max_offset - "
        "coalesce(staged_offsets.max_offset, raw_offsets.max_offset), 0)) "
        "AS average_offset_gap, "
        "max(dateDiff('second', staged_progress.staged_max_boundary, "
        "raw_latest.raw_max_boundary)) AS max_lag_seconds, "
        "avg(dateDiff('second', staged_progress.staged_max_boundary, "
        "raw_latest.raw_max_boundary)) AS average_lag_seconds "
        "FROM raw_offsets "
        f"LEFT JOIN staged_offsets USING ({REPLAY_PARTITION_COLUMN_NAME}) "
        f"LEFT JOIN active_offsets USING ({REPLAY_PARTITION_COLUMN_NAME}) "
        f"LEFT JOIN raw_latest USING ({REPLAY_PARTITION_COLUMN_NAME}) "
        f"LEFT JOIN staged_progress USING ({REPLAY_PARTITION_COLUMN_NAME})"
    )


def _raw_offsets_cte(raw_offsets_sql: str | None) -> str:
    if raw_offsets_sql is not None:
        return f"raw_offsets AS ({raw_offsets_sql}), "
    return (
        "raw_offsets AS ("
        f"SELECT toInt64(0) AS {REPLAY_PARTITION_COLUMN_NAME}, "
        "toInt64(0) AS max_offset WHERE 0), "
    )


def _raw_latest_cte(
    *, database: str, source_relation_name: str | None, boundary_column: str | None
) -> str:
    if source_relation_name is not None and boundary_column is not None:
        return (
            f"raw_latest AS (SELECT {REPLAY_PARTITION_COLUMN_NAME}, "
            f"max({boundary_column}) AS raw_max_boundary FROM "
            f"{database}.{source_relation_name} GROUP BY {REPLAY_PARTITION_COLUMN_NAME}), "
        )
    return (
        "raw_latest AS ("
        f"SELECT toInt64(0) AS {REPLAY_PARTITION_COLUMN_NAME}, "
        "CAST(NULL AS Nullable(DateTime64(3))) AS raw_max_boundary WHERE 0), "
    )


def _staged_progress_cte(staged_progress_sql: str | None) -> str:
    if staged_progress_sql is not None:
        return f"staged_progress AS ({staged_progress_sql}) "
    return (
        "staged_progress AS ("
        f"SELECT toInt64(0) AS {REPLAY_PARTITION_COLUMN_NAME}, "
        "CAST(NULL AS Nullable(DateTime64(3))) AS staged_max_boundary WHERE 0) "
    )


def _decode_count_row(row: Mapping[str, object]) -> ClickHouseReadinessCountRow:
    return ClickHouseReadinessCountRow(value=int(cast(int, row["value"])))


def _decode_column_row(row: Mapping[str, object]) -> ClickHouseReadinessColumnRow:
    return ClickHouseReadinessColumnRow(name=str(row["name"]))


def _decode_offset_row(row: Mapping[str, object]) -> ClickHouseReadinessOffsetRow:
    return ClickHouseReadinessOffsetRow(
        active_partition_count=int(cast(int, row["active_partition_count"])),
        staged_partition_count=int(cast(int, row["staged_partition_count"])),
        partitions_compared=int(cast(int, row["partitions_compared"])),
        missing_staged_partition_count=int(cast(int, row["missing_staged_partition_count"])),
        missing_freshness_partition_count=int(cast(int, row["missing_freshness_partition_count"])),
        lagging_partition_count=int(cast(int, row["lagging_partition_count"])),
        max_offset_gap=int(cast(int, row["max_offset_gap"])),
        average_offset_gap=float(cast(float, row["average_offset_gap"])),
        max_lag_seconds=(
            None if row["max_lag_seconds"] is None else float(cast(float, row["max_lag_seconds"]))
        ),
        average_lag_seconds=(
            None
            if row["average_lag_seconds"] is None
            else float(cast(float, row["average_lag_seconds"]))
        ),
    )


def _decode_scalar_row(row: Mapping[str, object]) -> ClickHouseReadinessScalarRow:
    return ClickHouseReadinessScalarRow(
        active_min_value=(
            None if row["active_min_value"] in BLANK_VALUES else str(row["active_min_value"])
        ),
        active_max_value=(
            None if row["active_max_value"] in BLANK_VALUES else str(row["active_max_value"])
        ),
        staged_min_value=(
            None if row["staged_min_value"] in BLANK_VALUES else str(row["staged_min_value"])
        ),
        staged_max_value=(
            None if row["staged_max_value"] in BLANK_VALUES else str(row["staged_max_value"])
        ),
        lag_seconds=None if row["lag_seconds"] is None else float(cast(float, row["lag_seconds"])),
    )


def _decode_create_query_row(
    row: Mapping[str, object],
) -> ClickHouseReadinessCreateQueryRow:
    return ClickHouseReadinessCreateQueryRow(create_table_query=str(row["create_table_query"]))
