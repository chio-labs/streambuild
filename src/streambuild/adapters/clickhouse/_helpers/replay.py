"""Execute neutral replay requests in ClickHouse."""

from __future__ import annotations

from streambuild.adapter.constants import DEPLOYMENT_BOUNDARY_TIME_KEY
from streambuild.adapter.exceptions import AdapterReplayError
from streambuild.adapter.models import (
    AdapterDeploymentReplayRequest,
    AdapterOwnershipReplayRequest,
    AdapterReplayBoundary,
    AdapterReplayRequest,
)
from streambuild.adapter.types import (
    AdapterReplayBoundaryMode,
    AdapterReplayLowerBoundMode,
    AdapterReplaySeedMode,
)
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


def render_clickhouse_replay_from_ownership(request: AdapterOwnershipReplayRequest) -> str:
    """Render one full replay whose inclusive cutoff is read inside ClickHouse."""

    replay: AdapterReplayRequest = request.replay
    if replay.mode == AdapterReplayBoundaryMode.OFFSETS:
        return _render_metadata_offset_replay(request)
    return _render_metadata_scalar_replay(request)


def render_clickhouse_replay_from_deployment(
    request: AdapterDeploymentReplayRequest,
) -> tuple[str, ...]:
    """Render seed and replay statements that read dynamic deployment metadata."""

    replay: AdapterReplayRequest = request.replay
    seed_sql: str | None = _render_deployment_seed(request)
    replay_sql: str = (
        _render_deployment_offset_replay(request)
        if replay.mode == AdapterReplayBoundaryMode.OFFSETS
        else _render_deployment_scalar_replay(request)
    )
    return (seed_sql, replay_sql) if seed_sql is not None else (replay_sql,)


def _render_deployment_offset_replay(request: AdapterDeploymentReplayRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    cutoff_cte: str = _deployment_offset_cutoff_cte(request)
    lower_cte: str | None = _deployment_offset_lower_cte(request)
    source_sql: str = _deployment_offset_source_sql(request=request, lower_cte=lower_cte)
    named_queries: tuple[SqlNamedQuery, ...] = (
        SqlNamedQuery(name="cutoff_offsets", query=cutoff_cte),
        *((SqlNamedQuery(name="active_start_offsets", query=lower_cte),) if lower_cte else ()),
        SqlNamedQuery(name="filtered_replay_source", query=source_sql),
    )
    query: str = _rewrite_replay_query(
        sql=replay.replay_query.query,
        relation_rewrites=(
            SqlRelationRewrite(
                source_name=replay.relations.source,
                target_relation="filtered_replay_source",
            ),
        ),
        prepend_ctes=named_queries,
    ).query
    return _build_replay_insert(request=replay, query=query)


def _render_deployment_scalar_replay(request: AdapterDeploymentReplayRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    column_type: str = _required_deployment_boundary_type(request)
    cutoff_cte: str = _deployment_scalar_cutoff_cte(request=request, column_type=column_type)
    lower_expression: str | None = _deployment_scalar_lower_expression(
        request=request,
        column_type=column_type,
    )
    upper_expression: str = "(SELECT cutoff_value FROM replay_cutoff)"
    named_queries: tuple[SqlNamedQuery, ...] = (
        SqlNamedQuery(name="replay_cutoff", query=cutoff_cte),
    )
    if replay.replay_query.aggregate_semantics:
        physical_predicate: str = _dynamic_scalar_predicate(
            column_name=f"anchor.{_physical_boundary_column(replay)}",
            upper_expression=upper_expression,
            lower_expression=lower_expression,
            inclusive=replay.window.lower_bound_inclusive,
        )
        source_sql: str = (
            f"SELECT anchor.* FROM {replay.database}.{replay.relations.anchor} AS anchor "
            f"WHERE {physical_predicate}"
        )
        query: str = _rewrite_replay_query(
            sql=replay.replay_query.query,
            relation_rewrites=(
                SqlRelationRewrite(
                    source_name=replay.relations.source,
                    target_relation=f"({source_sql})",
                ),
            ),
            prepend_ctes=named_queries,
        ).query
        return _build_replay_insert(request=replay, query=query)
    rewritten: str = _rewrite_replay_query(
        sql=replay.replay_query.query,
        relation_rewrites=(
            SqlRelationRewrite(
                source_name=replay.relations.source,
                target_relation=f"{replay.database}.{replay.relations.anchor}",
            ),
        ),
        predicate=_dynamic_scalar_predicate(
            column_name=_canonical_boundary_column(replay.mode),
            upper_expression=upper_expression,
            lower_expression=lower_expression,
            inclusive=replay.window.lower_bound_inclusive,
        ),
        prepend_ctes=named_queries,
    ).query
    return _build_replay_insert(request=replay, query=rewritten)


def _render_deployment_seed(request: AdapterDeploymentReplayRequest) -> str | None:
    replay: AdapterReplayRequest = request.replay
    if replay.seed_mode != AdapterReplaySeedMode.HISTORY_PREFIX:
        return None
    copyable_columns: tuple[str, ...] = tuple(
        name for name in replay.target_column_names if name in request.active_column_names
    )
    if not copyable_columns:
        return None
    column_list: str = ", ".join(copyable_columns)
    if replay.mode == AdapterReplayBoundaryMode.OFFSETS:
        lower_cte: str | None = _deployment_offset_lower_cte(request)
        if lower_cte is None:
            return None
        selected_columns: str = ", ".join(f"active.{name}" for name in copyable_columns)
        return (
            f"INSERT INTO {replay.database}.{replay.relations.target} ({column_list})\n"
            f"WITH active_start_offsets AS (\n{lower_cte}\n)\n"
            f"SELECT {selected_columns}\n"
            f"FROM {replay.database}.{request.active_relation_name} AS active\n"
            "INNER JOIN active_start_offsets\n"
            f"ON active.{_CANONICAL_REPLAY_PARTITION} = "
            f"active_start_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
            f"WHERE active.{_CANONICAL_REPLAY_OFFSET} "
            f"{'<' if replay.window.lower_bound_inclusive else '<='} "
            "active_start_offsets.start_offset"
        )
    column_type: str = _required_deployment_boundary_type(request)
    lower_expression: str | None = _deployment_scalar_lower_expression(
        request=request,
        column_type=column_type,
    )
    if lower_expression is None:
        return None
    return (
        f"INSERT INTO {replay.database}.{replay.relations.target} ({column_list})\n"
        f"SELECT {column_list}\n"
        f"FROM {replay.database}.{request.active_relation_name}\n"
        f"WHERE {_canonical_boundary_column(replay.mode)} "
        f"{'<' if replay.window.lower_bound_inclusive else '<='} {lower_expression}"
    )


def _deployment_offset_source_sql(
    *, request: AdapterDeploymentReplayRequest, lower_cte: str | None
) -> str:
    replay: AdapterReplayRequest = request.replay
    lower_join: str = _offset_lower_bound_join(
        source_alias="anchor",
        partition_column=replay.columns.partition,
        has_lower_bound=lower_cte is not None,
    )
    lower_clause: str = _offset_lower_bound_clause(
        source_alias="anchor",
        offset_column=replay.columns.offset,
        has_lower_bound=lower_cte is not None,
        inclusive=replay.window.lower_bound_inclusive,
    )
    upper_clause: str = _offset_upper_bound_clause(
        source_alias="anchor", offset_column=replay.columns.offset
    )
    selected_columns: str = ", ".join(
        f"anchor.{name} AS {name}" for name in request.anchor_column_names
    )
    return (
        f"SELECT {selected_columns}\n"
        f"FROM {replay.database}.{replay.relations.anchor} AS anchor\n"
        "INNER JOIN cutoff_offsets\n"
        f"ON anchor.{replay.columns.partition} = cutoff_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
        f"{lower_join}WHERE {upper_clause}\n{lower_clause}"
    ).rstrip()


def _deployment_offset_cutoff_cte(request: AdapterDeploymentReplayRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    return (
        "SELECT toInt64(splitByChar('=', boundary_key)[2]) AS "
        f"{_CANONICAL_REPLAY_PARTITION}, max(toInt64(cutoff_value)) AS cutoff_offset, "
        "true AS cutoff_inclusive\n"
        f"FROM {request.metadata_database}.streambuild_deployment_watermarks FINAL\n"
        f"WHERE deployment_id = '{_escape_literal(request.deployment_id)}' "
        f"AND root_object_name = '{_escape_literal(replay.relations.root)}' "
        f"AND boundary_key != '{DEPLOYMENT_BOUNDARY_TIME_KEY}'\n"
        f"GROUP BY {_CANONICAL_REPLAY_PARTITION}"
    )


def _deployment_offset_lower_cte(request: AdapterDeploymentReplayRequest) -> str | None:
    replay: AdapterReplayRequest = request.replay
    mode: AdapterReplayLowerBoundMode = replay.window.lower_bound_mode
    if mode == AdapterReplayLowerBoundMode.NONE:
        return None
    if mode == AdapterReplayLowerBoundMode.ACTIVE_FRONTIER:
        return (
            f"SELECT {_CANONICAL_REPLAY_PARTITION}, "
            f"max({_CANONICAL_REPLAY_OFFSET}) AS start_offset "
            f"FROM {replay.database}.{request.active_relation_name} "
            f"GROUP BY {_CANONICAL_REPLAY_PARTITION}"
        )
    lower_time: str = _deployment_lower_time_expression(request)
    time_column: str = replay.columns.landed_at or replay.columns.timestamp
    return (
        f"SELECT {replay.columns.partition} AS {_CANONICAL_REPLAY_PARTITION}, "
        f"max({replay.columns.offset}) AS start_offset "
        f"FROM {replay.database}.{replay.relations.anchor} "
        f"WHERE {time_column} <= {lower_time} GROUP BY {replay.columns.partition}"
    )


def _deployment_scalar_cutoff_cte(
    *, request: AdapterDeploymentReplayRequest, column_type: str
) -> str:
    replay: AdapterReplayRequest = request.replay
    boundary_key: str = _canonical_boundary_column(replay.mode)
    return (
        f"SELECT max(CAST(cutoff_value AS {column_type})) AS cutoff_value "
        f"FROM {request.metadata_database}.streambuild_deployment_watermarks FINAL "
        f"WHERE deployment_id = '{_escape_literal(request.deployment_id)}' "
        f"AND root_object_name = '{_escape_literal(replay.relations.root)}' "
        f"AND boundary_key = '{boundary_key}'"
    )


def _deployment_scalar_lower_expression(
    *, request: AdapterDeploymentReplayRequest, column_type: str
) -> str | None:
    replay: AdapterReplayRequest = request.replay
    mode: AdapterReplayLowerBoundMode = replay.window.lower_bound_mode
    if mode == AdapterReplayLowerBoundMode.NONE:
        return None
    if mode == AdapterReplayLowerBoundMode.ACTIVE_FRONTIER:
        return (
            f"(SELECT max({_canonical_boundary_column(replay.mode)}) "
            f"FROM {replay.database}.{request.active_relation_name})"
        )
    lower_time: str = _deployment_lower_time_expression(request)
    if replay.mode != AdapterReplayBoundaryMode.CURSOR:
        return f"CAST({lower_time} AS {column_type})"
    return (
        f"(SELECT min({replay.columns.cursor}) FROM {replay.database}.{replay.relations.anchor} "
        f"WHERE {replay.columns.timestamp} >= {lower_time} "
        f"AND {replay.columns.cursor} <= (SELECT cutoff_value FROM replay_cutoff))"
    )


def _deployment_lower_time_expression(request: AdapterDeploymentReplayRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    if replay.window.lower_bound_mode == AdapterReplayLowerBoundMode.FORCED_TIME:
        if replay.window.forced_start_time is None:
            raise AdapterReplayError("Forced deployment replay requires a start time")
        return f"toDateTime64('{_escape_literal(replay.window.forced_start_time)}', 3, 'UTC')"
    if replay.window.lookback_seconds is None:
        raise AdapterReplayError("Lookback deployment replay requires a duration")
    return (
        "(SELECT toDateTime64(cutoff_value, 3, 'UTC') - "
        f"toIntervalSecond({replay.window.lookback_seconds}) "
        f"FROM {request.metadata_database}.streambuild_deployment_watermarks FINAL "
        f"WHERE deployment_id = '{_escape_literal(request.deployment_id)}' "
        f"AND boundary_key = '{DEPLOYMENT_BOUNDARY_TIME_KEY}')"
    )


def _dynamic_scalar_predicate(
    *,
    column_name: str,
    upper_expression: str,
    lower_expression: str | None,
    inclusive: bool,
) -> str:
    upper: str = f"{column_name} <= {upper_expression}"
    if lower_expression is None:
        return upper
    return f"{column_name} {'>=' if inclusive else '>'} {lower_expression} AND {upper}"


def _required_deployment_boundary_type(request: AdapterDeploymentReplayRequest) -> str:
    if request.boundary_column_type is None:
        raise AdapterReplayError("Scalar deployment replay requires a resolved boundary type")
    return request.boundary_column_type


def _render_metadata_offset_replay(request: AdapterOwnershipReplayRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    coverage_cte: str = _ownership_coverage_cte(request)
    cutoff_cte: str = (
        "SELECT toInt64(splitByChar('=', JSONExtractString(coverage, 'boundary_key'))[2]) "
        f"AS {_CANONICAL_REPLAY_PARTITION}, "
        "max(toInt64(JSONExtractString(coverage, 'upper_value'))) AS cutoff_offset\n"
        f"FROM ownership_coverage\nGROUP BY {_CANONICAL_REPLAY_PARTITION}"
    )
    if replay.replay_query.aggregate_semantics:
        source_sql: str = (
            f"SELECT anchor.*\nFROM {replay.database}.{replay.relations.anchor} AS anchor\n"
            "INNER JOIN cutoff_offsets\n"
            f"ON anchor.{replay.columns.partition} = cutoff_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
            f"WHERE anchor.{replay.columns.offset} <= cutoff_offsets.cutoff_offset"
        )
        rewritten_query: str = _rewrite_replay_query(
            sql=replay.replay_query.query,
            relation_rewrites=(
                SqlRelationRewrite(
                    source_name=replay.relations.source,
                    target_relation=f"({source_sql})",
                ),
            ),
            prepend_ctes=(
                SqlNamedQuery(name="ownership_coverage", query=coverage_cte),
                SqlNamedQuery(name="cutoff_offsets", query=cutoff_cte),
            ),
        ).query
        return _build_replay_insert(request=replay, query=rewritten_query)
    replay_query: str = _rewrite_replay_query(
        sql=replay.replay_query.query,
        relation_rewrites=(
            SqlRelationRewrite(
                source_name=replay.relations.source,
                target_relation=f"{replay.database}.{replay.relations.anchor}",
            ),
        ),
    ).query
    wrapped_query: str = (
        f"WITH ownership_coverage AS (\n{coverage_cte}\n),\n"
        f"cutoff_offsets AS (\n{cutoff_cte}\n)\n"
        "SELECT replay_source.*\n"
        f"FROM (\n{replay_query}\n) AS replay_source\n"
        "INNER JOIN cutoff_offsets\n"
        f"ON replay_source.{_CANONICAL_REPLAY_PARTITION} = "
        f"cutoff_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
        f"WHERE replay_source.{_CANONICAL_REPLAY_OFFSET} <= cutoff_offsets.cutoff_offset"
    )
    return _build_replay_insert(
        request=replay,
        query=_rewrite_replay_query(sql=wrapped_query).query,
    )


def _render_metadata_scalar_replay(request: AdapterOwnershipReplayRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    column_type: str | None = request.boundary_column_type
    if column_type is None:
        raise AdapterReplayError("Scalar ownership replay requires a resolved boundary column type")
    coverage_cte: str = _ownership_coverage_cte(request)
    cutoff_cte: str = (
        "SELECT max(CAST(JSONExtractString(coverage, 'replay_cutoff_value') AS "
        f"{column_type})) AS cutoff_value FROM ownership_coverage"
    )
    physical_column: str = _physical_boundary_column(replay)
    if replay.replay_query.aggregate_semantics:
        source_sql: str = (
            f"SELECT anchor.*\nFROM {replay.database}.{replay.relations.anchor} AS anchor\n"
            "CROSS JOIN replay_cutoff\n"
            f"WHERE anchor.{physical_column} <= replay_cutoff.cutoff_value"
        )
        rewritten_query: str = _rewrite_replay_query(
            sql=replay.replay_query.query,
            relation_rewrites=(
                SqlRelationRewrite(
                    source_name=replay.relations.source,
                    target_relation=f"({source_sql})",
                ),
            ),
            prepend_ctes=(
                SqlNamedQuery(name="ownership_coverage", query=coverage_cte),
                SqlNamedQuery(name="replay_cutoff", query=cutoff_cte),
            ),
        ).query
        return _build_replay_insert(request=replay, query=rewritten_query)
    replay_query: str = _rewrite_replay_query(
        sql=replay.replay_query.query,
        relation_rewrites=(
            SqlRelationRewrite(
                source_name=replay.relations.source,
                target_relation=f"{replay.database}.{replay.relations.anchor}",
            ),
        ),
        predicate=(
            f"{_canonical_boundary_column(replay.mode)} <= (SELECT cutoff_value FROM replay_cutoff)"
        ),
        prepend_ctes=(
            SqlNamedQuery(name="ownership_coverage", query=coverage_cte),
            SqlNamedQuery(name="replay_cutoff", query=cutoff_cte),
        ),
    ).query
    return _build_replay_insert(request=replay, query=replay_query)


def _ownership_coverage_cte(request: AdapterOwnershipReplayRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    return (
        "SELECT arrayJoin(JSONExtractArrayRaw(argMax(replay_coverage_json, updated_at))) "
        "AS coverage\n"
        f"FROM {request.metadata_database}.streambuild_target_ownership\n"
        f"WHERE database_name = '{_escape_literal(replay.database)}' "
        f"AND relation_name = '{_escape_literal(replay.relations.target)}' "
        f"AND logical_model_name = '{_escape_literal(request.logical_model_name)}'"
    )


def _canonical_boundary_column(mode: AdapterReplayBoundaryMode) -> str:
    return {
        AdapterReplayBoundaryMode.CURSOR: "_replay_cursor",
        AdapterReplayBoundaryMode.TIMESTAMP: "_replay_timestamp",
        AdapterReplayBoundaryMode.LANDED_AT: "_replay_landed_at",
    }[mode]


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


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


def _physical_boundary_column(request: AdapterReplayRequest) -> str:
    return {
        AdapterReplayBoundaryMode.CURSOR: request.columns.cursor,
        AdapterReplayBoundaryMode.TIMESTAMP: request.columns.timestamp,
        AdapterReplayBoundaryMode.LANDED_AT: request.columns.landed_at,
    }[request.mode]


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
