"""Execute neutral replay requests in ClickHouse."""

from __future__ import annotations

from datetime import datetime, timedelta

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterReplayError
from streambuild.adapter.models import (
    AdapterQueryResult,
    AdapterReplayBoundary,
    AdapterReplayRequest,
)
from streambuild.adapter.types import (
    AdapterReplayBoundaryMode,
    AdapterReplayLowerBoundMode,
    AdapterReplaySeedMode,
)
from streambuild.adapters.clickhouse._helpers.catalog_parsing import extract_stable_binding
from streambuild.adapters.clickhouse.constants import CLICKHOUSE_VIEW_ENGINE
from streambuild.adapters.clickhouse.models import (
    ClickHouseReplayOffsetFrontier,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.main.build_insert_query import build_insert_query
from streambuild.compiler.sql_analysis.main.rewrite_query import rewrite_query
from streambuild.compiler.sql_analysis.models import (
    SqlNamedQuery,
    SqlQueryRewriteResult,
    SqlRelationRewrite,
)

_CANONICAL_REPLAY_PARTITION: str = "_replay_partition"
_CANONICAL_REPLAY_OFFSET: str = "_replay_offset"


def execute_clickhouse_replay(
    *, connection: AdapterConnection, request: AdapterReplayRequest
) -> None:
    """Seed and execute one replay request in ClickHouse."""

    active_relation_name: str = _active_relation_name(connection=connection, request=request)
    if request.mode == AdapterReplayBoundaryMode.OFFSETS:
        _execute_offset_replay(
            connection=connection,
            request=request,
            active_relation_name=active_relation_name,
        )
        return
    _execute_scalar_replay(
        connection=connection,
        request=request,
        active_relation_name=active_relation_name,
    )


def _execute_scalar_replay(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    active_relation_name: str,
) -> None:
    boundary: AdapterReplayBoundary = request.boundaries[0]
    boundary_column_type: str = _load_boundary_column_type(
        connection=connection,
        request=request,
    )
    lower_bound_value: str | None = _resolve_scalar_lower_bound(
        connection=connection,
        request=request,
        active_relation_name=active_relation_name,
        boundary=boundary,
        boundary_column_type=boundary_column_type,
    )
    if request.seed_mode == AdapterReplaySeedMode.HISTORY_PREFIX:
        _seed_scalar_prefix(
            connection=connection,
            request=request,
            active_relation_name=active_relation_name,
            boundary=boundary,
            boundary_column_type=boundary_column_type,
            lower_bound_value=lower_bound_value,
        )
    connection.command(
        _render_scalar_replay(
            request=request,
            boundary=boundary,
            boundary_column_type=boundary_column_type,
            lower_bound_value=lower_bound_value,
        )
    )


def _execute_offset_replay(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    active_relation_name: str,
) -> None:
    lower_bound_rows: tuple[ClickHouseReplayOffsetFrontier, ...] = _resolve_offset_lower_bounds(
        connection=connection,
        request=request,
        active_relation_name=active_relation_name,
    )
    if request.seed_mode == AdapterReplaySeedMode.HISTORY_PREFIX:
        _seed_offset_prefix(
            connection=connection,
            request=request,
            active_relation_name=active_relation_name,
            lower_bound_rows=lower_bound_rows,
        )
    connection.command(_render_offset_replay(request=request, lower_bound_rows=lower_bound_rows))


def _resolve_scalar_lower_bound(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    active_relation_name: str,
    boundary: AdapterReplayBoundary,
    boundary_column_type: str,
) -> str | None:
    lower_bound_mode: AdapterReplayLowerBoundMode = request.window.lower_bound_mode
    if lower_bound_mode == AdapterReplayLowerBoundMode.NONE:
        return None
    if lower_bound_mode == AdapterReplayLowerBoundMode.ACTIVE_FRONTIER:
        return _load_active_scalar_frontier(
            connection=connection,
            request=request,
            active_relation_name=active_relation_name,
            boundary_key=boundary.boundary_key,
        )
    lower_bound_time: str = _lower_bound_time(request)
    if request.mode == AdapterReplayBoundaryMode.CURSOR:
        return _load_cursor_lower_bound(
            connection=connection,
            request=request,
            lower_bound_time=lower_bound_time,
            cutoff_value=boundary.cutoff_value,
            cursor_column_type=boundary_column_type,
        )
    return lower_bound_time


def _resolve_offset_lower_bounds(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    active_relation_name: str,
) -> tuple[ClickHouseReplayOffsetFrontier, ...]:
    lower_bound_mode: AdapterReplayLowerBoundMode = request.window.lower_bound_mode
    if lower_bound_mode == AdapterReplayLowerBoundMode.NONE:
        return ()
    if lower_bound_mode == AdapterReplayLowerBoundMode.ACTIVE_FRONTIER:
        return _load_offset_frontiers(
            connection=connection,
            database=request.database,
            relation_name=active_relation_name,
            partition_column=_CANONICAL_REPLAY_PARTITION,
            offset_column=_CANONICAL_REPLAY_OFFSET,
            lower_bound_time=None,
            time_column=request.columns.landed_at,
        )
    return _load_offset_frontiers(
        connection=connection,
        database=request.database,
        relation_name=request.relations.anchor,
        partition_column=request.columns.partition,
        offset_column=request.columns.offset,
        lower_bound_time=_lower_bound_time(request),
        time_column=(
            request.columns.landed_at if request.columns.landed_at else request.columns.timestamp
        ),
    )


def _lower_bound_time(request: AdapterReplayRequest) -> str:
    if request.window.lower_bound_mode == AdapterReplayLowerBoundMode.FORCED_TIME:
        if request.window.forced_start_time is None:
            raise AdapterReplayError("Forced-time replay requires a start time")
        return request.window.forced_start_time
    if request.window.lookback_seconds is None:
        raise AdapterReplayError("Lookback replay requires a lookback duration")
    parsed_timestamp: datetime = datetime.strptime(
        request.window.boundary_time, "%Y-%m-%d %H:%M:%S.%f"
    )
    return (parsed_timestamp - timedelta(seconds=request.window.lookback_seconds)).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3]


def _render_scalar_replay(
    *,
    request: AdapterReplayRequest,
    boundary: AdapterReplayBoundary,
    boundary_column_type: str,
    lower_bound_value: str | None,
) -> str:
    source_rewrite: SqlRelationRewrite = SqlRelationRewrite(
        source_name=request.relations.source,
        target_relation=f"{request.database}.{request.relations.anchor}",
    )
    rewritten_query: str = _rewrite_replay_query(
        sql=request.replay_query.query,
        relation_rewrites=(source_rewrite,),
    ).query
    if not boundary.cutoff_value:
        empty_query: str = _rewrite_replay_query(
            sql=f"SELECT * FROM ({rewritten_query}) WHERE 0"
        ).query
        return _build_replay_insert(
            request=request,
            query=empty_query,
        )
    canonical_predicate: str = _scalar_boundary_predicate(
        column_name=boundary.boundary_key,
        boundary=boundary,
        boundary_column_type=boundary_column_type,
        lower_bound_value=lower_bound_value,
        lower_bound_inclusive=request.window.lower_bound_inclusive,
    )
    if request.replay_query.aggregate_semantics:
        physical_predicate: str = _scalar_boundary_predicate(
            column_name=f"anchor.{_physical_boundary_column(request)}",
            boundary=boundary,
            boundary_column_type=boundary_column_type,
            lower_bound_value=lower_bound_value,
            lower_bound_inclusive=request.window.lower_bound_inclusive,
        )
        filtered_anchor: str = _rewrite_replay_query(
            sql=(
                f"SELECT anchor.* FROM {request.database}.{request.relations.anchor} AS anchor "
                f"WHERE {physical_predicate}"
            )
        ).query
        rewritten_query = _rewrite_replay_query(
            sql=request.replay_query.query,
            relation_rewrites=(
                SqlRelationRewrite(
                    source_name=request.relations.source,
                    target_relation=f"({filtered_anchor})",
                ),
            ),
        ).query
    else:
        rewritten_query = _rewrite_replay_query(
            sql=rewritten_query,
            predicate=canonical_predicate,
        ).query
    return _build_replay_insert(request=request, query=rewritten_query)


def _scalar_boundary_predicate(
    *,
    column_name: str,
    boundary: AdapterReplayBoundary,
    boundary_column_type: str,
    lower_bound_value: str | None,
    lower_bound_inclusive: bool,
) -> str:
    upper_operator: str = "<=" if boundary.cutoff_inclusive else "<"
    upper_predicate: str = (
        f"{column_name} {upper_operator} "
        f"{_render_cast_literal(value=boundary.cutoff_value, column_type=boundary_column_type)}"
    )
    if lower_bound_value is None:
        return upper_predicate
    lower_operator: str = ">=" if lower_bound_inclusive else ">"
    return (
        f"{column_name} {lower_operator} "
        f"{_render_cast_literal(value=lower_bound_value, column_type=boundary_column_type)} "
        f"AND {upper_predicate}"
    )


def _render_offset_replay(
    *,
    request: AdapterReplayRequest,
    lower_bound_rows: tuple[ClickHouseReplayOffsetFrontier, ...],
) -> str:
    cutoff_cte_sql: str = _offset_frontier_cte(
        boundaries=request.boundaries,
        value_alias="cutoff_offset",
    )
    lower_bound_cte_sql: str = _lower_offset_frontier_cte(lower_bound_rows)
    if request.replay_query.aggregate_semantics:
        return _render_aggregate_offset_replay(
            request=request,
            cutoff_cte_sql=cutoff_cte_sql,
            lower_bound_cte_sql=lower_bound_cte_sql,
            has_lower_bound=bool(lower_bound_rows),
        )
    replay_query: str = _rewrite_replay_query(
        sql=request.replay_query.query,
        relation_rewrites=(
            SqlRelationRewrite(
                source_name=request.relations.source,
                target_relation=f"{request.database}.{request.relations.anchor}",
            ),
        ),
    ).query
    lower_bound_clause: str = _offset_lower_bound_clause(
        source_alias="replay_source",
        offset_column=_CANONICAL_REPLAY_OFFSET,
        has_lower_bound=bool(lower_bound_rows),
        inclusive=request.window.lower_bound_inclusive,
    )
    lower_bound_cte: str = (
        f",\nactive_start_offsets AS (\n{lower_bound_cte_sql}\n)\n" if lower_bound_rows else ""
    )
    lower_bound_join: str = _offset_lower_bound_join(
        source_alias="replay_source",
        partition_column=_CANONICAL_REPLAY_PARTITION,
        has_lower_bound=bool(lower_bound_rows),
    )
    upper_bound_clause: str = _offset_upper_bound_clause(
        source_alias="replay_source",
        offset_column=_CANONICAL_REPLAY_OFFSET,
    )
    wrapped_query: str = (
        f"WITH cutoff_offsets AS (\n{cutoff_cte_sql}\n)"
        f"{lower_bound_cte}"
        "SELECT replay_source.*\n"
        f"FROM (\n{replay_query}\n) AS replay_source\n"
        "INNER JOIN cutoff_offsets\n"
        f"ON replay_source.{_CANONICAL_REPLAY_PARTITION} = "
        f"cutoff_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
        f"{lower_bound_join}"
        f"WHERE {upper_bound_clause}\n"
        f"{lower_bound_clause}".rstrip()
    )
    return _build_replay_insert(
        request=request,
        query=_rewrite_replay_query(sql=wrapped_query).query,
    )


def _render_aggregate_offset_replay(
    *,
    request: AdapterReplayRequest,
    cutoff_cte_sql: str,
    lower_bound_cte_sql: str,
    has_lower_bound: bool,
) -> str:
    lower_bound_join: str = _offset_lower_bound_join(
        source_alias="anchor",
        partition_column=request.columns.partition,
        has_lower_bound=has_lower_bound,
    )
    lower_bound_clause: str = _offset_lower_bound_clause(
        source_alias="anchor",
        offset_column=request.columns.offset,
        has_lower_bound=has_lower_bound,
        inclusive=request.window.lower_bound_inclusive,
    )
    upper_bound_clause: str = _offset_upper_bound_clause(
        source_alias="anchor",
        offset_column=request.columns.offset,
    )
    source_sql: str = (
        f"SELECT anchor.*\n"
        f"FROM {request.database}.{request.relations.anchor} AS anchor\n"
        "INNER JOIN cutoff_offsets\n"
        f"ON anchor.{request.columns.partition} = "
        f"cutoff_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
        f"{lower_bound_join}"
        f"WHERE {upper_bound_clause}\n"
        f"{lower_bound_clause}"
    ).rstrip()
    named_queries: tuple[SqlNamedQuery, ...] = (
        SqlNamedQuery(name="cutoff_offsets", query=cutoff_cte_sql),
        *(
            (SqlNamedQuery(name="active_start_offsets", query=lower_bound_cte_sql),)
            if has_lower_bound
            else ()
        ),
    )
    rewritten_query: str = _rewrite_replay_query(
        sql=request.replay_query.query,
        relation_rewrites=(
            SqlRelationRewrite(
                source_name=request.relations.source,
                target_relation=f"({source_sql})",
            ),
        ),
        prepend_ctes=named_queries,
    ).query
    return _build_replay_insert(
        request=request,
        query=rewritten_query,
    )


def _seed_scalar_prefix(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    active_relation_name: str,
    boundary: AdapterReplayBoundary,
    boundary_column_type: str,
    lower_bound_value: str | None,
) -> None:
    if lower_bound_value is None:
        return
    copyable_columns: tuple[str, ...] = _copyable_columns(
        connection=connection,
        request=request,
        active_relation_name=active_relation_name,
    )
    if not copyable_columns:
        return
    column_list: str = ", ".join(copyable_columns)
    connection.command(
        f"INSERT INTO {request.database}.{request.relations.target} ({column_list})\n"
        f"SELECT {column_list}\n"
        f"FROM {request.database}.{active_relation_name}\n"
        f"WHERE {boundary.boundary_key} "
        f"{'<' if request.window.lower_bound_inclusive else '<='} "
        f"{_render_cast_literal(value=lower_bound_value, column_type=boundary_column_type)}"
    )


def _seed_offset_prefix(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    active_relation_name: str,
    lower_bound_rows: tuple[ClickHouseReplayOffsetFrontier, ...],
) -> None:
    if not lower_bound_rows:
        return
    live_columns: frozenset[str] = _relation_columns(
        connection=connection,
        database=request.database,
        relation_name=active_relation_name,
    )
    if not {_CANONICAL_REPLAY_PARTITION, _CANONICAL_REPLAY_OFFSET}.issubset(live_columns):
        raise AdapterReplayError(
            "Seeded bounded offset replay requires the active table to preserve "
            f"{_CANONICAL_REPLAY_PARTITION} and {_CANONICAL_REPLAY_OFFSET}"
        )
    copyable_columns: tuple[str, ...] = tuple(
        name for name in request.target_column_names if name in live_columns
    )
    if not copyable_columns:
        return
    column_list: str = ", ".join(copyable_columns)
    selected_columns: str = ", ".join(f"active.{name}" for name in copyable_columns)
    lower_bound_cte: str = _lower_offset_frontier_cte(lower_bound_rows)
    connection.command(
        f"INSERT INTO {request.database}.{request.relations.target} ({column_list})\n"
        f"WITH active_start_offsets AS (\n{lower_bound_cte}\n)\n"
        f"SELECT {selected_columns}\n"
        f"FROM {request.database}.{active_relation_name} AS active\n"
        "INNER JOIN active_start_offsets\n"
        f"ON active.{_CANONICAL_REPLAY_PARTITION} = "
        f"active_start_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
        f"WHERE active.{_CANONICAL_REPLAY_OFFSET} "
        f"{'<' if request.window.lower_bound_inclusive else '<='} "
        "active_start_offsets.start_offset"
    )


def _copyable_columns(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    active_relation_name: str,
) -> tuple[str, ...]:
    live_columns: frozenset[str] = _relation_columns(
        connection=connection,
        database=request.database,
        relation_name=active_relation_name,
    )
    return tuple(name for name in request.target_column_names if name in live_columns)


def _active_relation_name(*, connection: AdapterConnection, request: AdapterReplayRequest) -> str:
    result: AdapterQueryResult = connection.query(
        "SELECT as_select FROM system.tables "
        f"WHERE database = '{request.database}' AND engine = '{CLICKHOUSE_VIEW_ENGINE}' "
        f"AND name = '{request.relations.root}'"
    )
    if not result.rows:
        return request.relations.root
    binding: str | None = extract_stable_binding(
        engine=CLICKHOUSE_VIEW_ENGINE,
        as_select=str(result.rows[0][0]),
    )
    return binding or request.relations.root


def _load_active_scalar_frontier(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    active_relation_name: str,
    boundary_key: str,
) -> str | None:
    result: AdapterQueryResult = connection.query(
        f"SELECT max({boundary_key}) AS cutoff_value FROM {request.database}.{active_relation_name}"
    )
    if not result.rows or result.rows[0][0] is None:
        return None
    return str(result.rows[0][0])


def _load_offset_frontiers(
    *,
    connection: AdapterConnection,
    database: str,
    relation_name: str,
    partition_column: str,
    offset_column: str,
    lower_bound_time: str | None,
    time_column: str,
) -> tuple[ClickHouseReplayOffsetFrontier, ...]:
    where_sql: str = (
        ""
        if lower_bound_time is None
        else f" WHERE {time_column} <= CAST('{lower_bound_time}' AS DateTime64(3))"
    )
    result: AdapterQueryResult = connection.query(
        f"SELECT {partition_column}, max({offset_column}) AS cutoff_offset "
        f"FROM {database}.{relation_name}{where_sql} GROUP BY {partition_column}"
    )
    return tuple(
        ClickHouseReplayOffsetFrontier(partition=row[0], cutoff_offset=str(row[1]))
        for row in result.rows
    )


def _load_cursor_lower_bound(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
    lower_bound_time: str,
    cutoff_value: str,
    cursor_column_type: str,
) -> str | None:
    result: AdapterQueryResult = connection.query(
        f"SELECT min({request.columns.cursor}) AS lower_bound_cursor "
        f"FROM {request.database}.{request.relations.anchor} "
        f"WHERE {request.columns.timestamp} >= CAST('{lower_bound_time}' AS DateTime64(3)) "
        f"AND {request.columns.cursor} <= "
        f"{_render_cast_literal(value=cutoff_value, column_type=cursor_column_type)}"
    )
    if not result.rows or result.rows[0][0] is None:
        return None
    return str(result.rows[0][0])


def _load_boundary_column_type(
    *,
    connection: AdapterConnection,
    request: AdapterReplayRequest,
) -> str:
    physical_boundary_key: str = _physical_boundary_column(request)
    result: AdapterQueryResult = connection.query(
        "SELECT name, type FROM system.columns "
        f"WHERE database = '{request.database}' AND table = '{request.relations.anchor}' "
        f"AND name = '{physical_boundary_key}'"
    )
    if not result.rows:
        raise AdapterReplayError(
            "Could not resolve boundary column type for '"
            f"{physical_boundary_key}' on {request.database}.{request.relations.anchor}"
        )
    return str(result.rows[0][1])


def _physical_boundary_column(request: AdapterReplayRequest) -> str:
    return {
        AdapterReplayBoundaryMode.CURSOR: request.columns.cursor,
        AdapterReplayBoundaryMode.TIMESTAMP: request.columns.timestamp,
        AdapterReplayBoundaryMode.LANDED_AT: request.columns.landed_at,
    }[request.mode]


def _relation_columns(
    *, connection: AdapterConnection, database: str, relation_name: str
) -> frozenset[str]:
    result: AdapterQueryResult = connection.query(f"DESCRIBE TABLE {database}.{relation_name}")
    return frozenset(str(row[0]) for row in result.rows)


def _rewrite_replay_query(
    *,
    sql: str,
    relation_rewrites: tuple[SqlRelationRewrite, ...] = (),
    predicate: str | None = None,
    prepend_ctes: tuple[SqlNamedQuery, ...] = (),
) -> SqlQueryRewriteResult:
    try:
        return rewrite_query(
            sql=sql,
            dialect="clickhouse",
            relation_rewrites=relation_rewrites,
            predicate=predicate,
            prepend_ctes=prepend_ctes,
        )
    except SqlAnalysisError as error:
        raise AdapterReplayError(f"Replay SQL could not be rewritten: {error}") from None


def _build_replay_insert(*, request: AdapterReplayRequest, query: str) -> str:
    try:
        return build_insert_query(
            target_relation=f"{request.database}.{request.relations.target}",
            query=query,
            dialect="clickhouse",
        )
    except SqlAnalysisError as error:
        raise AdapterReplayError(f"Replay SQL could not be generated: {error}") from None


def _offset_frontier_cte(*, boundaries: tuple[AdapterReplayBoundary, ...], value_alias: str) -> str:
    return "\nUNION ALL\n".join(
        "SELECT "
        f"{boundary.partition_value} AS {_CANONICAL_REPLAY_PARTITION}, "
        f"{boundary.cutoff_value} AS {value_alias}, "
        f"{'true' if boundary.cutoff_inclusive else 'false'} AS cutoff_inclusive"
        for boundary in boundaries
    )


def _lower_offset_frontier_cte(
    rows: tuple[ClickHouseReplayOffsetFrontier, ...],
) -> str:
    return "\nUNION ALL\n".join(
        "SELECT "
        f"{row.partition} AS {_CANONICAL_REPLAY_PARTITION}, "
        f"{row.cutoff_offset} AS start_offset"
        for row in rows
    )


def _offset_lower_bound_join(
    *, source_alias: str, partition_column: str, has_lower_bound: bool
) -> str:
    if not has_lower_bound:
        return ""
    return (
        "LEFT JOIN active_start_offsets\n"
        f"ON {source_alias}.{partition_column} = "
        f"active_start_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
    )


def _offset_lower_bound_clause(
    *, source_alias: str, offset_column: str, has_lower_bound: bool, inclusive: bool
) -> str:
    if not has_lower_bound:
        return ""
    return (
        "  AND (active_start_offsets.start_offset IS NULL "
        f"OR {source_alias}.{offset_column} "
        f"{'>=' if inclusive else '>'} active_start_offsets.start_offset)\n"
    )


def _offset_upper_bound_clause(*, source_alias: str, offset_column: str) -> str:
    return (
        f"((cutoff_offsets.cutoff_inclusive AND {source_alias}.{offset_column} "
        "<= cutoff_offsets.cutoff_offset) OR "
        f"(NOT cutoff_offsets.cutoff_inclusive AND {source_alias}.{offset_column} "
        "< cutoff_offsets.cutoff_offset))"
    )


def _render_cast_literal(*, value: str, column_type: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"CAST('{escaped_value}' AS {column_type})"
