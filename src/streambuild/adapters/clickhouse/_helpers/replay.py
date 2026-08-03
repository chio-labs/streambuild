"""Execute neutral replay requests in ClickHouse."""

from __future__ import annotations

from streambuild.adapter.constants import (
    METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME,
    METADATA_DEPLOYMENTS_TABLE_NAME,
    METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME,
    METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME,
)
from streambuild.adapter.exceptions import AdapterReplayError
from streambuild.adapter.models import (
    AdapterDeploymentReplayRequest,
    AdapterOwnershipReplayRequest,
    AdapterReplayBoundary,
    AdapterReplayCoverageRequest,
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


def render_clickhouse_replay_coverage_query(request: AdapterReplayCoverageRequest) -> str:
    """Render ownership-compatible coverage for the rows selected by one replay window."""

    if request.replay.mode == AdapterReplayBoundaryMode.OFFSETS:
        return _offset_coverage_query(request.replay)
    return _scalar_coverage_query(request)


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
        "SELECT toInt64(partition_value) AS "
        f"{_CANONICAL_REPLAY_PARTITION}, max(toInt64(cutoff_value)) AS cutoff_offset, "
        "true AS cutoff_inclusive\n"
        f"FROM {request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME}\n"
        f"WHERE deployment_id = '{_escape_literal(request.deployment_id)}' "
        f"AND root_object_name = '{_escape_literal(replay.relations.root)}' "
        "AND boundary_kind = 'offsets'\n"
        f"GROUP BY {_CANONICAL_REPLAY_PARTITION}"
    )


def _deployment_offset_lower_cte(request: AdapterDeploymentReplayRequest) -> str | None:
    replay: AdapterReplayRequest = request.replay
    lookback_time_expression: str | None = (
        _deployment_lookback_time_expression(request)
        if replay.window.lower_bound_mode == AdapterReplayLowerBoundMode.LOOKBACK
        else None
    )
    return _replay_offset_lower_cte(
        replay=replay,
        active_relation_name=request.active_relation_name,
        lookback_time_expression=lookback_time_expression,
    )


def _replay_offset_lower_cte(
    *,
    replay: AdapterReplayRequest,
    active_relation_name: str | None,
    lookback_time_expression: str | None,
) -> str | None:
    mode: AdapterReplayLowerBoundMode = replay.window.lower_bound_mode
    if mode == AdapterReplayLowerBoundMode.NONE:
        return None
    if mode == AdapterReplayLowerBoundMode.ACTIVE_FRONTIER:
        active_name: str = _required_active_relation_name(active_relation_name=active_relation_name)
        return (
            f"SELECT {_CANONICAL_REPLAY_PARTITION}, "
            f"max({_CANONICAL_REPLAY_OFFSET}) AS start_offset "
            f"FROM {replay.database}.{active_name} "
            f"GROUP BY {_CANONICAL_REPLAY_PARTITION}"
        )
    lower_time: str = _replay_lower_time_expression(
        replay=replay,
        lookback_time_expression=lookback_time_expression,
    )
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
    return (
        f"SELECT max(CAST(cutoff_value AS {column_type})) AS cutoff_value "
        f"FROM {request.metadata_database}.{METADATA_DEPLOYMENT_WATERMARKS_TABLE_NAME} "
        f"WHERE deployment_id = '{_escape_literal(request.deployment_id)}' "
        f"AND root_object_name = '{_escape_literal(replay.relations.root)}' "
        f"AND boundary_kind = '{_escape_literal(str(replay.mode))}'"
    )


def _deployment_scalar_lower_expression(
    *, request: AdapterDeploymentReplayRequest, column_type: str
) -> str | None:
    replay: AdapterReplayRequest = request.replay
    lookback_time_expression: str | None = (
        _deployment_lookback_time_expression(request)
        if replay.window.lower_bound_mode == AdapterReplayLowerBoundMode.LOOKBACK
        else None
    )
    return _replay_scalar_lower_expression(
        replay=replay,
        column_type=column_type,
        active_relation_name=request.active_relation_name,
        lookback_time_expression=lookback_time_expression,
        upper_expression="(SELECT cutoff_value FROM replay_cutoff)",
    )


def _replay_scalar_lower_expression(
    *,
    replay: AdapterReplayRequest,
    column_type: str,
    active_relation_name: str | None,
    lookback_time_expression: str | None,
    upper_expression: str,
) -> str | None:
    mode: AdapterReplayLowerBoundMode = replay.window.lower_bound_mode
    if mode == AdapterReplayLowerBoundMode.NONE:
        return None
    if mode == AdapterReplayLowerBoundMode.ACTIVE_FRONTIER:
        active_name: str = _required_active_relation_name(active_relation_name=active_relation_name)
        return (
            f"(SELECT max({_canonical_boundary_column(replay.mode)}) "
            f"FROM {replay.database}.{active_name})"
        )
    lower_time: str = _replay_lower_time_expression(
        replay=replay,
        lookback_time_expression=lookback_time_expression,
    )
    if replay.mode != AdapterReplayBoundaryMode.CURSOR:
        return f"CAST({lower_time} AS {column_type})"
    return (
        f"(SELECT minOrNull({replay.columns.cursor}) "
        f"FROM {replay.database}.{replay.relations.anchor} "
        f"WHERE {replay.columns.timestamp} >= {lower_time} "
        f"AND {replay.columns.cursor} <= {upper_expression})"
    )


def _replay_lower_time_expression(
    *, replay: AdapterReplayRequest, lookback_time_expression: str | None
) -> str:
    if replay.window.lower_bound_mode == AdapterReplayLowerBoundMode.FORCED_TIME:
        if replay.window.forced_start_time is None:
            raise AdapterReplayError("Forced replay requires a start time")
        return f"toDateTime64('{_escape_literal(replay.window.forced_start_time)}', 3, 'UTC')"
    if lookback_time_expression is None:
        raise AdapterReplayError("Lookback replay requires a lower-time expression")
    return lookback_time_expression


def _deployment_lookback_time_expression(request: AdapterDeploymentReplayRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    if replay.window.lookback_seconds is None:
        raise AdapterReplayError("Lookback deployment replay requires a duration")
    return (
        "(SELECT any(boundary_time) - "
        f"toIntervalSecond({replay.window.lookback_seconds}) "
        f"FROM {request.metadata_database}.{METADATA_DEPLOYMENTS_TABLE_NAME} "
        f"WHERE deployment_id = '{_escape_literal(request.deployment_id)}')"
    )


def _required_active_relation_name(*, active_relation_name: str | None) -> str:
    if active_relation_name is None:
        raise AdapterReplayError("Active-frontier replay requires an active relation")
    return active_relation_name


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
    lower: str = _scalar_lower_predicate(
        column_name=column_name,
        lower_expression=lower_expression,
        inclusive=inclusive,
    )
    return f"{lower} AND {upper}"


def _scalar_lower_predicate(*, column_name: str, lower_expression: str, inclusive: bool) -> str:
    return f"{column_name} {'>=' if inclusive else '>'} {lower_expression}"


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
    lower_cte: str | None = _replay_offset_lower_cte(
        replay=replay,
        active_relation_name=None,
        lookback_time_expression=None,
    )
    if replay.replay_query.aggregate_semantics:
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
        source_sql: str = (
            f"SELECT anchor.*\nFROM {replay.database}.{replay.relations.anchor} AS anchor\n"
            "INNER JOIN cutoff_offsets\n"
            f"ON anchor.{replay.columns.partition} = cutoff_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
            f"{lower_join}"
            f"WHERE anchor.{replay.columns.offset} <= cutoff_offsets.cutoff_offset\n"
            f"{lower_clause}"
        ).rstrip()
        named_queries: tuple[SqlNamedQuery, ...] = (
            SqlNamedQuery(name="ownership_coverage", query=coverage_cte),
            SqlNamedQuery(name="cutoff_offsets", query=cutoff_cte),
            *((SqlNamedQuery(name="active_start_offsets", query=lower_cte),) if lower_cte else ()),
        )
        rewritten_query: str = _rewrite_replay_query(
            sql=replay.replay_query.query,
            relation_rewrites=(
                SqlRelationRewrite(
                    source_name=replay.relations.source,
                    target_relation=f"({source_sql})",
                ),
            ),
            prepend_ctes=named_queries,
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
    lower_cte_sql: str = (
        f",\nactive_start_offsets AS (\n{lower_cte}\n)\n" if lower_cte is not None else "\n"
    )
    lower_join = _offset_lower_bound_join(
        source_alias="replay_source",
        partition_column=_CANONICAL_REPLAY_PARTITION,
        has_lower_bound=lower_cte is not None,
    )
    lower_clause = _offset_lower_bound_clause(
        source_alias="replay_source",
        offset_column=_CANONICAL_REPLAY_OFFSET,
        has_lower_bound=lower_cte is not None,
        inclusive=replay.window.lower_bound_inclusive,
    )
    wrapped_query: str = (
        f"WITH ownership_coverage AS (\n{coverage_cte}\n),\n"
        f"cutoff_offsets AS (\n{cutoff_cte}\n)"
        f"{lower_cte_sql}"
        "SELECT replay_source.*\n"
        f"FROM (\n{replay_query}\n) AS replay_source\n"
        "INNER JOIN cutoff_offsets\n"
        f"ON replay_source.{_CANONICAL_REPLAY_PARTITION} = "
        f"cutoff_offsets.{_CANONICAL_REPLAY_PARTITION}\n"
        f"{lower_join}"
        f"WHERE replay_source.{_CANONICAL_REPLAY_OFFSET} <= cutoff_offsets.cutoff_offset\n"
        f"{lower_clause}"
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
    upper_expression: str = "(SELECT cutoff_value FROM replay_cutoff)"
    lower_expression: str | None = _replay_scalar_lower_expression(
        replay=replay,
        column_type=column_type,
        active_relation_name=None,
        lookback_time_expression=None,
        upper_expression=upper_expression,
    )
    if replay.replay_query.aggregate_semantics:
        physical_predicate: str = _dynamic_scalar_predicate(
            column_name=f"anchor.{physical_column}",
            upper_expression="replay_cutoff.cutoff_value",
            lower_expression=lower_expression,
            inclusive=replay.window.lower_bound_inclusive,
        )
        source_sql: str = (
            f"SELECT anchor.*\nFROM {replay.database}.{replay.relations.anchor} AS anchor\n"
            "CROSS JOIN replay_cutoff\n"
            f"WHERE {physical_predicate}"
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
        predicate=_dynamic_scalar_predicate(
            column_name=_canonical_boundary_column(replay.mode),
            upper_expression=upper_expression,
            lower_expression=lower_expression,
            inclusive=replay.window.lower_bound_inclusive,
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
        "WITH current_target AS (SELECT argMax(tuple(event_kind, replay_set_id), "
        "tuple(recorded_at, event_id)) AS current_state FROM "
        f"{request.metadata_database}.{METADATA_DIRECT_TARGET_EVENTS_TABLE_NAME} "
        f"WHERE database_name = '{_escape_literal(replay.database)}' AND relation_name = "
        f"'{_escape_literal(replay.relations.target)}')\n"
        "SELECT DISTINCT toJSONString(map('driving_input_relation_name', "
        "driving_input_relation_name, "
        "'replay_boundary_mode', replay_boundary_mode, 'boundary_key', "
        "if(replay_boundary_mode = 'offsets', concat('_replay_partition=', partition_value), "
        "concat('_replay_', replay_boundary_mode)), 'source_partition_column_name', "
        "coalesce(source_partition_column_name, ''), 'source_position_column_name', "
        "source_position_column_name, 'source_timestamp_column_name', "
        "coalesce(source_timestamp_column_name, ''), 'lower_value', lower_value, "
        "'upper_value', upper_value, 'replay_cutoff_value', replay_cutoff_value)) AS coverage\n"
        f"FROM {request.metadata_database}.{METADATA_DIRECT_REPLAY_RANGES_TABLE_NAME} "
        "CROSS JOIN current_target WHERE replay_set_id = current_target.current_state.2 "
        f"AND target_database_name = '{_escape_literal(replay.database)}' "
        "AND range_present AND logical_model_name = "
        f"'{_escape_literal(request.logical_model_name)}' "
        "AND current_target.current_state.1 != 'released'"
    )


def _offset_coverage_query(replay: AdapterReplayRequest) -> str:
    timestamp_column: str = replay.columns.timestamp or ""
    lower_cte: str | None = _replay_offset_lower_cte(
        replay=replay,
        active_relation_name=None,
        lookback_time_expression=None,
    )
    if lower_cte is None:
        return _full_offset_coverage_query(replay=replay, timestamp_column=timestamp_column)
    lower_join: str = _offset_lower_bound_join(
        source_alias="anchor",
        partition_column=replay.columns.partition,
        has_lower_bound=lower_cte is not None,
        lower_alias="coverage_start_offsets",
    )
    lower_clause: str = _offset_lower_bound_clause(
        source_alias="anchor",
        offset_column=replay.columns.offset,
        has_lower_bound=lower_cte is not None,
        inclusive=replay.window.lower_bound_inclusive,
        lower_alias="coverage_start_offsets",
    )
    lower_prefix: str = (
        f"WITH active_start_offsets AS (\n{lower_cte}\n)\n" if lower_cte is not None else ""
    )
    return (
        f"{lower_prefix}"
        "SELECT toJSONString(groupArray(map("
        f"'driving_input_relation_name', '{_escape_literal(replay.relations.anchor)}', "
        "'replay_boundary_mode', 'offsets', "
        "'boundary_key', concat('_replay_partition=', toString(partition_value)), "
        f"'source_partition_column_name', '{_escape_literal(replay.columns.partition)}', "
        f"'source_position_column_name', '{_escape_literal(replay.columns.offset)}', "
        f"'source_timestamp_column_name', '{_escape_literal(timestamp_column)}', "
        "'lower_value', toString(lower_value), 'upper_value', toString(upper_value)))) AS value\n"
        "FROM (\n"
        f"SELECT partition_value, min(offset_value) AS lower_value, "
        "max(offset_value) AS upper_value\nFROM (\n"
        f"SELECT {replay.columns.partition} AS partition_value, "
        f"{replay.columns.offset} AS offset_value, {replay.columns.offset} - "
        f"toInt64(row_number() OVER (PARTITION BY {replay.columns.partition} "
        f"ORDER BY {replay.columns.offset})) AS sequence_group\n"
        f"FROM (SELECT DISTINCT anchor.{replay.columns.partition} AS {replay.columns.partition}, "
        f"anchor.{replay.columns.offset} AS {replay.columns.offset} "
        f"FROM {replay.database}.{replay.relations.anchor} AS anchor\n"
        f"{lower_join}"
        f"WHERE true\n{lower_clause})\n)\n"
        "GROUP BY partition_value, sequence_group\nORDER BY partition_value, lower_value\n)"
    )


def _full_offset_coverage_query(*, replay: AdapterReplayRequest, timestamp_column: str) -> str:
    return (
        "SELECT toJSONString(groupArray(map("
        f"'driving_input_relation_name', '{_escape_literal(replay.relations.anchor)}', "
        "'replay_boundary_mode', 'offsets', "
        "'boundary_key', concat('_replay_partition=', toString(partition_value)), "
        f"'source_partition_column_name', '{_escape_literal(replay.columns.partition)}', "
        f"'source_position_column_name', '{_escape_literal(replay.columns.offset)}', "
        f"'source_timestamp_column_name', '{_escape_literal(timestamp_column)}', "
        "'lower_value', toString(lower_value), 'upper_value', toString(upper_value)))) AS value\n"
        "FROM (\n"
        f"SELECT partition_value, min(offset_value) AS lower_value, "
        "max(offset_value) AS upper_value\nFROM (\n"
        f"SELECT {replay.columns.partition} AS partition_value, "
        f"{replay.columns.offset} AS offset_value, {replay.columns.offset} - "
        f"toInt64(row_number() OVER (PARTITION BY {replay.columns.partition} "
        f"ORDER BY {replay.columns.offset})) AS sequence_group\n"
        f"FROM (SELECT DISTINCT {replay.columns.partition}, {replay.columns.offset} "
        f"FROM {replay.database}.{replay.relations.anchor})\n)\n"
        "GROUP BY partition_value, sequence_group\nORDER BY partition_value, lower_value\n)"
    )


def _scalar_coverage_query(request: AdapterReplayCoverageRequest) -> str:
    replay: AdapterReplayRequest = request.replay
    position_column: str = _physical_boundary_column(replay)
    canonical_key: str = _canonical_boundary_column(replay.mode)
    if replay.window.lower_bound_mode == AdapterReplayLowerBoundMode.NONE:
        return _full_scalar_coverage_query(
            replay=replay,
            position_column=position_column,
            canonical_key=canonical_key,
        )
    upper_expression: str = "(SELECT cutoff_value FROM replay_cutoff)"
    lower_expression: str | None = _replay_scalar_lower_expression(
        replay=replay,
        column_type=_required_coverage_boundary_type(request),
        active_relation_name=None,
        lookback_time_expression=None,
        upper_expression=upper_expression,
    )
    coverage_predicate: str = _dynamic_scalar_predicate(
        column_name=position_column,
        upper_expression=upper_expression,
        lower_expression=lower_expression,
        inclusive=replay.window.lower_bound_inclusive,
    )
    cutoff_query: str = (
        f"SELECT max({position_column}) AS cutoff_value "
        f"FROM {replay.database}.{replay.relations.anchor}"
        if replay.mode == AdapterReplayBoundaryMode.CURSOR
        else "SELECT now64(3, 'UTC') AS cutoff_value"
    )
    cutoff_prefix: str = f"WITH replay_cutoff AS ({cutoff_query})\n"
    return (
        f"{cutoff_prefix}"
        "SELECT toJSONString(groupArray(map("
        f"'driving_input_relation_name', '{_escape_literal(replay.relations.anchor)}', "
        f"'replay_boundary_mode', '{replay.mode}', 'boundary_key', '{canonical_key}', "
        "'source_partition_column_name', '', "
        f"'source_position_column_name', '{_escape_literal(position_column)}', "
        f"'source_timestamp_column_name', '{_escape_literal(replay.columns.timestamp)}', "
        "'lower_value', toString(lower_value), 'upper_value', toString(upper_value), "
        "'replay_cutoff_value', toString(cutoff_value)))) AS value\n"
        f"FROM (SELECT min({position_column}) AS lower_value, "
        f"max({position_column}) AS upper_value, {upper_expression} AS cutoff_value "
        f"FROM {replay.database}.{replay.relations.anchor} WHERE {coverage_predicate} "
        "HAVING count() > 0)"
    )


def _full_scalar_coverage_query(
    *, replay: AdapterReplayRequest, position_column: str, canonical_key: str
) -> str:
    cutoff_expression: str = (
        f"max({position_column})"
        if replay.mode == AdapterReplayBoundaryMode.CURSOR
        else "now64(3, 'UTC')"
    )
    return (
        "SELECT toJSONString(groupArray(map("
        f"'driving_input_relation_name', '{_escape_literal(replay.relations.anchor)}', "
        f"'replay_boundary_mode', '{replay.mode}', 'boundary_key', '{canonical_key}', "
        "'source_partition_column_name', '', "
        f"'source_position_column_name', '{_escape_literal(position_column)}', "
        f"'source_timestamp_column_name', '{_escape_literal(replay.columns.timestamp)}', "
        "'lower_value', toString(lower_value), 'upper_value', toString(upper_value), "
        "'replay_cutoff_value', toString(cutoff_value)))) AS value\n"
        f"FROM (SELECT min({position_column}) AS lower_value, "
        f"max({position_column}) AS upper_value, {cutoff_expression} AS cutoff_value "
        f"FROM {replay.database}.{replay.relations.anchor} HAVING count() > 0)"
    )


def _required_coverage_boundary_type(request: AdapterReplayCoverageRequest) -> str:
    if request.boundary_column_type is None:
        raise AdapterReplayError("Scalar replay coverage requires a resolved boundary type")
    return request.boundary_column_type


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
    *,
    source_alias: str,
    partition_column: str,
    has_lower_bound: bool,
    lower_alias: str | None = None,
) -> str:
    if not has_lower_bound:
        return ""
    lower_relation: str = (
        "active_start_offsets" if lower_alias is None else f"active_start_offsets AS {lower_alias}"
    )
    lower_reference: str = lower_alias or "active_start_offsets"
    return (
        f"LEFT JOIN {lower_relation}\n"
        f"ON {source_alias}.{partition_column} = "
        f"{lower_reference}.{_CANONICAL_REPLAY_PARTITION}\n"
    )


def _offset_lower_bound_clause(
    *,
    source_alias: str,
    offset_column: str,
    has_lower_bound: bool,
    inclusive: bool,
    lower_alias: str | None = None,
) -> str:
    if not has_lower_bound:
        return ""
    lower_reference: str = lower_alias or "active_start_offsets"
    return (
        f"  AND ({lower_reference}.start_offset IS NULL "
        f"OR {source_alias}.{offset_column} "
        f"{'>=' if inclusive else '>'} {lower_reference}.start_offset)\n"
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
