"""Replay execution helpers for staged backfill."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

from sqlglot import exp, parse_one

from streambuild.clickhouse.inspect.main.inspect_managed_table_state import (
    inspect_managed_table_state,
)
from streambuild.clickhouse.inspect.models import InspectedActiveTableBinding
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ExternalSourceReplayConfig,
    ObjectKey,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.metadata_state.models import DeploymentWatermarkRecord
from streambuild.compiler.planner.constants import (
    REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
)
from streambuild.compiler.planner.models import DeploymentPlan, RebuildSubtree
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.backfill.models import (
    ActiveOffsetFrontierQueryRow,
    ActiveScalarFrontierQueryRow,
    CursorLowerBoundQueryRow,
    TableColumnSystemRow,
)
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def execute_scalar_replay(
    *,
    client: ClickHouseClient,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    default_database: str,
    replay_lineage_mode: ReplayLineageMode | str,
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...],
    boundary_time: str,
) -> None:
    """Replay historical rows for scalar replay-lineage modes."""

    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    if resolved_replay_lineage_mode not in {
        ReplayLineageMode.TIMESTAMP,
        ReplayLineageMode.LANDED_AT,
        ReplayLineageMode.CURSOR,
    }:
        raise BackfillExecutionError(f"Scalar replay does not support mode '{replay_lineage_mode}'")

    shadow_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name
        for prepared in deployment_plan.prepared_shadow_objects
    }
    watermark_by_root: dict[ObjectKey, DeploymentWatermarkRecord] = {
        watermark.root_key: watermark for watermark in deployment_watermarks
    }
    root_table_by_key: dict[ObjectKey, DesiredTable] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
    }
    root_materialized_view_by_target_name: dict[str, DesiredMaterializedView] = {
        object_.target_table_name: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredMaterializedView)
    }
    replay_table_name_by_logical_name: dict[str, str] = _build_replay_table_name_by_logical_name(
        desired_state=desired_state,
        deployment_plan=deployment_plan,
    )
    subtree: RebuildSubtree
    for subtree in deployment_plan.rebuild_subtrees:
        root_table: DesiredTable = root_table_by_key[subtree.root_key]
        root_materialized_view: DesiredMaterializedView = root_materialized_view_by_target_name[
            root_table.name
        ]
        watermark: DeploymentWatermarkRecord = watermark_by_root[subtree.root_key]
        shadow_target_name: str = shadow_name_by_key[subtree.root_key]
        anchor_table_name: str = shadow_name_by_key.get(
            subtree.upstream_boundary_key,
            subtree.upstream_boundary_key.name,
        )
        database: str = root_table.key.database or default_database
        active_table_name: str = _active_table_name_for_logical_root(
            client=client,
            database=database,
            logical_table_name=root_table.name,
        )
        external_source_replay_config: ExternalSourceReplayConfig | None = (
            _external_source_replay_config_for_key(
                desired_state=desired_state,
                key=subtree.upstream_boundary_key,
            )
        )
        boundary_column_type: str = _load_scalar_boundary_column_type(
            client=client,
            database=database,
            table_name=anchor_table_name,
            boundary_key=watermark.boundary_key,
            external_source_replay_config=external_source_replay_config,
        )
        lower_bound_value: str | None = None
        lower_bound_key: str = watermark.boundary_key
        lower_bound_column_type: str = boundary_column_type
        if subtree.forced_start_time is not None:
            if resolved_replay_lineage_mode == ReplayLineageMode.CURSOR:
                lower_bound_value, _ = _load_cursor_lower_bound_at_boundary_time(
                    client=client,
                    database=database,
                    anchor_table_name=anchor_table_name,
                    lower_bound_time=subtree.forced_start_time,
                    cutoff_value=watermark.cutoff_value,
                    cursor_column_name=(
                        external_source_replay_config.cursor_column_name
                        if external_source_replay_config is not None
                        and external_source_replay_config.cursor_column_name is not None
                        else REPLAY_CURSOR_COLUMN_NAME
                    ),
                    timestamp_column_name=(
                        external_source_replay_config.timestamp_column_name
                        if external_source_replay_config is not None
                        and external_source_replay_config.timestamp_column_name is not None
                        else REPLAY_TIMESTAMP_COLUMN_NAME
                    ),
                    cursor_column_type=boundary_column_type,
                )
            else:
                lower_bound_value = subtree.forced_start_time
        elif subtree.execution_lookback_seconds is not None:
            if resolved_replay_lineage_mode == ReplayLineageMode.CURSOR:
                lower_bound_value, _ = _load_cursor_lower_bound_at_boundary_time(
                    client=client,
                    database=database,
                    anchor_table_name=anchor_table_name,
                    lower_bound_time=_subtract_seconds_from_timestamp(
                        timestamp_value=boundary_time,
                        seconds=subtree.execution_lookback_seconds,
                    ),
                    cutoff_value=watermark.cutoff_value,
                    cursor_column_name=(
                        external_source_replay_config.cursor_column_name
                        if external_source_replay_config is not None
                        and external_source_replay_config.cursor_column_name is not None
                        else REPLAY_CURSOR_COLUMN_NAME
                    ),
                    timestamp_column_name=(
                        external_source_replay_config.timestamp_column_name
                        if external_source_replay_config is not None
                        and external_source_replay_config.timestamp_column_name is not None
                        else REPLAY_TIMESTAMP_COLUMN_NAME
                    ),
                    cursor_column_type=boundary_column_type,
                )
            else:
                lower_bound_value = _subtract_seconds_from_timestamp(
                    timestamp_value=boundary_time,
                    seconds=subtree.execution_lookback_seconds,
                )
        elif subtree.execution_mode in {
            REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
            REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
        }:
            lower_bound_value = _load_active_scalar_frontier(
                client=client,
                database=database,
                live_table_name=active_table_name,
                boundary_key=watermark.boundary_key,
            )
        if subtree.execution_mode == REBUILD_EXECUTION_MODE_SEEDED_BOUNDED:
            _seed_scalar_prefix_if_needed(
                client=client,
                root_table=root_table,
                shadow_target_name=shadow_target_name,
                database=database,
                live_table_name=active_table_name,
                boundary_key=lower_bound_key,
                boundary_column_type=lower_bound_column_type,
                lower_bound_value=lower_bound_value,
            )
        client.command(
            _render_scalar_replay_statement(
                root_materialized_view=root_materialized_view,
                shadow_target_name=shadow_target_name,
                anchor_table_name=anchor_table_name,
                database=database,
                replay_table_name_by_logical_name=replay_table_name_by_logical_name,
                boundary_key=watermark.boundary_key,
                boundary_column_type=boundary_column_type,
                cutoff_value=watermark.cutoff_value,
                lower_bound_value=lower_bound_value,
            )
        )


def execute_offset_replay(
    *,
    client: ClickHouseClient,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    default_database: str,
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...],
    boundary_time: str,
) -> None:
    """Replay historical rows for offset-based replay mode."""

    shadow_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name
        for prepared in deployment_plan.prepared_shadow_objects
    }
    watermark_by_root: dict[ObjectKey, tuple[DeploymentWatermarkRecord, ...]] = {}
    subtree: RebuildSubtree
    for subtree in deployment_plan.rebuild_subtrees:
        collected_watermarks: list[DeploymentWatermarkRecord] = []
        watermark: DeploymentWatermarkRecord
        for watermark in deployment_watermarks:
            if watermark.root_key == subtree.root_key:
                collected_watermarks.append(watermark)
        watermark_by_root[subtree.root_key] = tuple(collected_watermarks)
    root_table_by_key: dict[ObjectKey, DesiredTable] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
    }
    root_materialized_view_by_target_name: dict[str, DesiredMaterializedView] = {
        object_.target_table_name: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredMaterializedView)
    }
    replay_table_name_by_logical_name: dict[str, str] = _build_replay_table_name_by_logical_name(
        desired_state=desired_state,
        deployment_plan=deployment_plan,
    )
    for subtree in deployment_plan.rebuild_subtrees:
        root_table: DesiredTable = root_table_by_key[subtree.root_key]
        root_materialized_view: DesiredMaterializedView = root_materialized_view_by_target_name[
            root_table.name
        ]
        root_watermarks: tuple[DeploymentWatermarkRecord, ...] = watermark_by_root[subtree.root_key]
        if not root_watermarks:
            continue
        shadow_target_name: str = shadow_name_by_key[subtree.root_key]
        anchor_table_name: str = shadow_name_by_key.get(
            subtree.upstream_boundary_key,
            subtree.upstream_boundary_key.name,
        )
        database: str = root_table.key.database or default_database
        active_table_name: str = _active_table_name_for_logical_root(
            client=client,
            database=database,
            logical_table_name=root_table.name,
        )
        lower_bound_rows: tuple[ActiveOffsetFrontierQueryRow, ...] = ()
        if subtree.forced_start_time is not None:
            external_source_replay_config: ExternalSourceReplayConfig | None = (
                _external_source_replay_config_for_key(
                    desired_state=desired_state,
                    key=subtree.upstream_boundary_key,
                )
            )
            lower_bound_rows = _load_offset_frontiers_at_boundary_time(
                client=client,
                database=database,
                anchor_table_name=anchor_table_name,
                lower_bound_time=subtree.forced_start_time,
                partition_column_name=(
                    external_source_replay_config.partition_column_name
                    if external_source_replay_config is not None
                    and external_source_replay_config.partition_column_name is not None
                    else REPLAY_PARTITION_COLUMN_NAME
                ),
                offset_column_name=(
                    external_source_replay_config.offset_column_name
                    if external_source_replay_config is not None
                    and external_source_replay_config.offset_column_name is not None
                    else REPLAY_OFFSET_COLUMN_NAME
                ),
                boundary_time_column_name=(
                    external_source_replay_config.landed_at_column_name
                    if external_source_replay_config is not None
                    and external_source_replay_config.landed_at_column_name is not None
                    else (
                        external_source_replay_config.timestamp_column_name
                        if external_source_replay_config is not None
                        and external_source_replay_config.timestamp_column_name is not None
                        else REPLAY_LANDED_AT_COLUMN_NAME
                    )
                ),
            )
        elif subtree.execution_lookback_seconds is not None:
            external_source_replay_config = _external_source_replay_config_for_key(
                desired_state=desired_state,
                key=subtree.upstream_boundary_key,
            )
            lower_bound_rows = _load_offset_frontiers_at_boundary_time(
                client=client,
                database=database,
                anchor_table_name=anchor_table_name,
                lower_bound_time=_subtract_seconds_from_timestamp(
                    timestamp_value=boundary_time,
                    seconds=subtree.execution_lookback_seconds,
                ),
                partition_column_name=(
                    external_source_replay_config.partition_column_name
                    if external_source_replay_config is not None
                    and external_source_replay_config.partition_column_name is not None
                    else REPLAY_PARTITION_COLUMN_NAME
                ),
                offset_column_name=(
                    external_source_replay_config.offset_column_name
                    if external_source_replay_config is not None
                    and external_source_replay_config.offset_column_name is not None
                    else REPLAY_OFFSET_COLUMN_NAME
                ),
                boundary_time_column_name=(
                    external_source_replay_config.landed_at_column_name
                    if external_source_replay_config is not None
                    and external_source_replay_config.landed_at_column_name is not None
                    else (
                        external_source_replay_config.timestamp_column_name
                        if external_source_replay_config is not None
                        and external_source_replay_config.timestamp_column_name is not None
                        else REPLAY_LANDED_AT_COLUMN_NAME
                    )
                ),
            )
        elif subtree.execution_mode in {
            REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
            REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
        }:
            lower_bound_rows = _load_active_offset_frontiers(
                client=client,
                database=database,
                live_table_name=active_table_name,
            )
        if subtree.execution_mode == REBUILD_EXECUTION_MODE_SEEDED_BOUNDED:
            _seed_offset_prefix_if_needed(
                client=client,
                root_table=root_table,
                shadow_target_name=shadow_target_name,
                database=database,
                live_table_name=active_table_name,
                lower_bound_rows=lower_bound_rows,
            )
        client.command(
            _render_offset_replay_statement(
                root_materialized_view=root_materialized_view,
                shadow_target_name=shadow_target_name,
                anchor_table_name=anchor_table_name,
                database=database,
                replay_table_name_by_logical_name=replay_table_name_by_logical_name,
                deployment_watermarks=root_watermarks,
                lower_bound_rows=lower_bound_rows,
            )
        )


def _render_scalar_replay_statement(
    *,
    root_materialized_view: DesiredMaterializedView,
    shadow_target_name: str,
    anchor_table_name: str,
    database: str,
    replay_table_name_by_logical_name: Mapping[str, str],
    boundary_key: str,
    boundary_column_type: str,
    cutoff_value: str,
    lower_bound_value: str | None = None,
) -> str:
    parsed_expression: object = parse_one(
        root_materialized_view.query,
        dialect="clickhouse",
    )
    if not isinstance(parsed_expression, exp.Select):
        raise BackfillExecutionError("Scalar replay expects a SELECT query")
    expression: exp.Select = parsed_expression
    _rewrite_replay_reference_tables(
        expression=expression,
        source_table_name=root_materialized_view.source_table_name,
        database=database,
        replay_table_name_by_logical_name=replay_table_name_by_logical_name,
    )
    for table in expression.find_all(exp.Table):
        if table.name != root_materialized_view.source_table_name:
            continue
        table.set("this", exp.to_identifier(anchor_table_name))
        table.set("db", exp.to_identifier(database))

    if not cutoff_value:
        return (
            f"INSERT INTO {database}.{shadow_target_name}\n"
            f"SELECT * FROM ({expression.sql(dialect='clickhouse')}) WHERE 0"
        )

    replay_boundary_expression: exp.Condition = exp.LTE(
        this=exp.column(boundary_key),
        expression=parse_one(
            _render_cast_literal(value=cutoff_value, column_type=boundary_column_type),
            dialect="clickhouse",
        ),
    )
    if lower_bound_value is not None:
        replay_boundary_expression = exp.and_(
            exp.GTE(
                this=exp.column(boundary_key),
                expression=parse_one(
                    _render_cast_literal(value=lower_bound_value, column_type=boundary_column_type),
                    dialect="clickhouse",
                ),
            ),
            replay_boundary_expression,
        )
    existing_where: exp.Where | None = expression.args.get("where")
    if existing_where is None:
        expression.set("where", exp.Where(this=replay_boundary_expression))
    else:
        expression.set(
            "where",
            exp.Where(
                this=exp.and_(existing_where.this, replay_boundary_expression),
            ),
        )

    return f"INSERT INTO {database}.{shadow_target_name}\n{expression.sql(dialect='clickhouse')}"


def _render_offset_replay_statement(
    *,
    root_materialized_view: DesiredMaterializedView,
    shadow_target_name: str,
    anchor_table_name: str,
    database: str,
    replay_table_name_by_logical_name: Mapping[str, str],
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...],
    lower_bound_rows: tuple[ActiveOffsetFrontierQueryRow, ...] = (),
) -> str:
    parsed_expression: object = parse_one(
        root_materialized_view.query,
        dialect="clickhouse",
    )
    if not isinstance(parsed_expression, exp.Select):
        raise BackfillExecutionError("Offset replay expects a SELECT query")
    expression: exp.Select = parsed_expression
    _rewrite_replay_reference_tables(
        expression=expression,
        source_table_name=root_materialized_view.source_table_name,
        database=database,
        replay_table_name_by_logical_name=replay_table_name_by_logical_name,
    )
    cutoff_rows: list[str] = []
    watermark: DeploymentWatermarkRecord
    for watermark in deployment_watermarks:
        partition_value: str = watermark.boundary_key.split("=", 1)[1]
        cutoff_rows.append(
            "SELECT "
            f"{partition_value} AS {REPLAY_PARTITION_COLUMN_NAME}, "
            f"{watermark.cutoff_value} AS cutoff_offset"
        )
    cutoff_cte_sql: str = "\nUNION ALL\n".join(cutoff_rows)
    lower_bound_select_rows: list[str] = []
    lower_bound_where_sql: str = ""
    if lower_bound_rows:
        lower_bound_row: ActiveOffsetFrontierQueryRow
        for lower_bound_row in lower_bound_rows:
            lower_bound_select_rows.append(
                "SELECT "
                f"{lower_bound_row._replay_partition} AS {REPLAY_PARTITION_COLUMN_NAME}, "
                f"{lower_bound_row.cutoff_offset} AS start_offset"
            )
        lower_bound_where_sql = (
            "  AND (active_start_offsets.start_offset IS NULL "
            f"OR anchor.{REPLAY_OFFSET_COLUMN_NAME} >= active_start_offsets.start_offset)\n"
        )

    if _offset_replay_query_has_aggregate_semantics(expression):
        for table in expression.find_all(exp.Table):
            if table.name != root_materialized_view.source_table_name:
                continue
            source_alias: exp.TableAlias | None = table.args.get("alias")
            source_subquery_sql: str = (
                f"SELECT anchor.*\n"
                f"FROM {database}.{anchor_table_name} AS anchor\n"
                "INNER JOIN cutoff_offsets\n"
                "ON anchor."
                + REPLAY_PARTITION_COLUMN_NAME
                + " = cutoff_offsets."
                + REPLAY_PARTITION_COLUMN_NAME
                + "\n"
                + (
                    "LEFT JOIN active_start_offsets\n"
                    + "ON anchor."
                    + REPLAY_PARTITION_COLUMN_NAME
                    + " = active_start_offsets."
                    + REPLAY_PARTITION_COLUMN_NAME
                    + "\n"
                    if lower_bound_rows
                    else ""
                )
                + f"WHERE anchor.{REPLAY_OFFSET_COLUMN_NAME} <= cutoff_offsets.cutoff_offset\n"
                + lower_bound_where_sql
            ).rstrip()
            table.replace(
                exp.Subquery(
                    this=parse_one(source_subquery_sql, dialect="clickhouse"),
                    alias=None if source_alias is None else source_alias.copy(),
                )
            )
            break

        cte_expressions: list[exp.CTE] = [
            exp.CTE(
                this=parse_one(cutoff_cte_sql, dialect="clickhouse"),
                alias=exp.TableAlias(this=exp.to_identifier("cutoff_offsets")),
            ),
        ]
        if lower_bound_rows:
            cte_expressions.insert(
                1,
                exp.CTE(
                    this=parse_one(
                        "\nUNION ALL\n".join(lower_bound_select_rows), dialect="clickhouse"
                    ),
                    alias=exp.TableAlias(this=exp.to_identifier("active_start_offsets")),
                ),
            )
        existing_with: exp.With | None = expression.args.get("with_")
        if existing_with is None:
            expression.set("with_", exp.With(expressions=cte_expressions))
        else:
            existing_with.set("expressions", [*cte_expressions, *existing_with.expressions])

        return (
            f"INSERT INTO {database}.{shadow_target_name}\n{expression.sql(dialect='clickhouse')}"
        )

    for table in expression.find_all(exp.Table):
        if table.name != root_materialized_view.source_table_name:
            continue
        table.set("this", exp.to_identifier(anchor_table_name))
        table.set("db", exp.to_identifier(database))
        break

    lower_bound_cte_sql: str = ""
    lower_bound_join_sql: str = ""
    rendered_lower_bound_where_sql: str = ""
    if lower_bound_rows:
        lower_bound_cte_sql = (
            ",\nactive_start_offsets AS (\n"
            + "\nUNION ALL\n".join(lower_bound_select_rows)
            + "\n)\n"
        )
        lower_bound_join_sql = (
            "LEFT JOIN active_start_offsets\n"
            + "ON replay_source."
            + REPLAY_PARTITION_COLUMN_NAME
            + " = active_start_offsets."
            + REPLAY_PARTITION_COLUMN_NAME
            + "\n"
        )
        rendered_lower_bound_where_sql = lower_bound_where_sql.replace(
            f"anchor.{REPLAY_OFFSET_COLUMN_NAME}",
            f"replay_source.{REPLAY_OFFSET_COLUMN_NAME}",
        )

    return (
        f"INSERT INTO {database}.{shadow_target_name}\n"
        f"WITH cutoff_offsets AS (\n{cutoff_cte_sql}\n)"
        f"{lower_bound_cte_sql}"
        "SELECT replay_source.*\n"
        f"FROM (\n{expression.sql(dialect='clickhouse')}\n) AS replay_source\n"
        "INNER JOIN cutoff_offsets\n"
        + "ON replay_source."
        + REPLAY_PARTITION_COLUMN_NAME
        + " = cutoff_offsets."
        + REPLAY_PARTITION_COLUMN_NAME
        + "\n"
        f"{lower_bound_join_sql}"
        f"WHERE replay_source.{REPLAY_OFFSET_COLUMN_NAME} <= cutoff_offsets.cutoff_offset\n"
        f"{rendered_lower_bound_where_sql}".rstrip()
    )


def _build_replay_table_name_by_logical_name(
    *,
    desired_state: DesiredState,
    deployment_plan: DeploymentPlan,
) -> dict[str, str]:
    prepared_table_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name
        for prepared in deployment_plan.prepared_shadow_objects
        if prepared.logical_key.object_type == DESIRED_OBJECT_TYPE_TABLE
    }
    return {
        object_.name: prepared_table_name_by_key.get(object_.key, object_.name)
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
    }


def _rewrite_replay_reference_tables(
    *,
    expression: exp.Select,
    source_table_name: str,
    database: str,
    replay_table_name_by_logical_name: Mapping[str, str],
) -> None:
    table: exp.Table
    for table in expression.find_all(exp.Table):
        if table.name == source_table_name:
            continue
        replay_table_name: str | None = replay_table_name_by_logical_name.get(table.name)
        if replay_table_name is None:
            continue
        table.set("this", exp.to_identifier(replay_table_name))
        table.set("db", exp.to_identifier(database))


def _offset_replay_query_has_aggregate_semantics(expression: exp.Select) -> bool:
    if expression.find(exp.Group) is not None:
        return True
    return expression.find(exp.AggFunc) is not None


def _seed_scalar_prefix_if_needed(
    *,
    client: ClickHouseClient,
    root_table: DesiredTable,
    shadow_target_name: str,
    database: str,
    live_table_name: str,
    boundary_key: str,
    boundary_column_type: str,
    lower_bound_value: str | None,
) -> None:
    if lower_bound_value is None:
        return
    copyable_column_names: tuple[str, ...] = _copyable_column_names(
        client=client,
        database=database,
        live_table_name=live_table_name,
        desired_column_names=tuple(column.name for column in root_table.columns),
    )
    if not copyable_column_names:
        return
    client.command(
        _render_seeded_scalar_prefix_copy_statement(
            shadow_target_name=shadow_target_name,
            live_table_name=live_table_name,
            database=database,
            boundary_key=boundary_key,
            boundary_column_type=boundary_column_type,
            lower_bound_value=lower_bound_value,
            copyable_column_names=copyable_column_names,
        )
    )


def _seed_offset_prefix_if_needed(
    *,
    client: ClickHouseClient,
    root_table: DesiredTable,
    shadow_target_name: str,
    database: str,
    live_table_name: str,
    lower_bound_rows: tuple[ActiveOffsetFrontierQueryRow, ...],
) -> None:
    if not lower_bound_rows:
        return
    live_column_names: set[str] = _live_column_names(
        client=client,
        database=database,
        live_table_name=live_table_name,
    )
    if not {REPLAY_PARTITION_COLUMN_NAME, REPLAY_OFFSET_COLUMN_NAME}.issubset(live_column_names):
        raise BackfillExecutionError(
            "Seeded bounded offset replay requires the active table to preserve "
            f"{REPLAY_PARTITION_COLUMN_NAME} and {REPLAY_OFFSET_COLUMN_NAME}"
        )
    copyable_column_names: tuple[str, ...] = _copyable_column_names(
        client=client,
        database=database,
        live_table_name=live_table_name,
        desired_column_names=tuple(column.name for column in root_table.columns),
    )
    if not copyable_column_names:
        return
    client.command(
        _render_seeded_offset_prefix_copy_statement(
            shadow_target_name=shadow_target_name,
            live_table_name=live_table_name,
            database=database,
            lower_bound_rows=lower_bound_rows,
            copyable_column_names=copyable_column_names,
        )
    )


def _copyable_column_names(
    *,
    client: ClickHouseClient,
    database: str,
    live_table_name: str,
    desired_column_names: tuple[str, ...],
) -> tuple[str, ...]:
    live_column_names: set[str] = _live_column_names(
        client=client,
        database=database,
        live_table_name=live_table_name,
    )
    return tuple(
        column_name for column_name in desired_column_names if column_name in live_column_names
    )


def _live_column_names(
    *,
    client: ClickHouseClient,
    database: str,
    live_table_name: str,
) -> set[str]:
    live_columns: tuple[TableColumnSystemRow, ...] = client.query_many(
        statement=f"DESCRIBE TABLE {database}.{live_table_name}",
        decode=_decode_table_column_system_row,
    )
    return {column.name for column in live_columns}


def _active_table_name_for_logical_root(
    *, client: ClickHouseClient, database: str, logical_table_name: str
) -> str:
    active_bindings: tuple[InspectedActiveTableBinding, ...] = inspect_managed_table_state(
        client=client,
        database=database,
    ).active_bindings
    binding: InspectedActiveTableBinding
    for binding in active_bindings:
        if binding.logical_name == logical_table_name:
            return binding.physical_name
    return logical_table_name


def _load_active_scalar_frontier(
    *,
    client: ClickHouseClient,
    database: str,
    live_table_name: str,
    boundary_key: str,
) -> str | None:
    row: ActiveScalarFrontierQueryRow | None = client.query_one(
        statement=f"SELECT max({boundary_key}) AS cutoff_value FROM {database}.{live_table_name}",
        decode=_decode_active_scalar_frontier_query_row,
    )
    if row is None:
        return None
    return row.cutoff_value


def _load_active_offset_frontiers(
    *,
    client: ClickHouseClient,
    database: str,
    live_table_name: str,
) -> tuple[ActiveOffsetFrontierQueryRow, ...]:
    return client.query_many(
        statement=f"SELECT {REPLAY_PARTITION_COLUMN_NAME}, "
        f"max({REPLAY_OFFSET_COLUMN_NAME}) AS cutoff_offset "
        f"FROM {database}.{live_table_name} GROUP BY {REPLAY_PARTITION_COLUMN_NAME}",
        decode=_decode_active_offset_frontier_query_row,
    )


def _load_offset_frontiers_at_boundary_time(
    *,
    client: ClickHouseClient,
    database: str,
    anchor_table_name: str,
    lower_bound_time: str,
    partition_column_name: str = REPLAY_PARTITION_COLUMN_NAME,
    offset_column_name: str = REPLAY_OFFSET_COLUMN_NAME,
    boundary_time_column_name: str = REPLAY_LANDED_AT_COLUMN_NAME,
) -> tuple[ActiveOffsetFrontierQueryRow, ...]:
    select_sql: str = (
        f"SELECT {partition_column_name} AS {REPLAY_PARTITION_COLUMN_NAME}, "
        f"max({offset_column_name}) AS cutoff_offset "
    )
    return client.query_many(
        statement=select_sql + f"FROM {database}.{anchor_table_name} "
        f"WHERE {boundary_time_column_name} <= CAST('{lower_bound_time}' AS DateTime64(3)) "
        f"GROUP BY {partition_column_name}",
        decode=_decode_active_offset_frontier_query_row,
    )


def _load_cursor_lower_bound_at_boundary_time(
    *,
    client: ClickHouseClient,
    database: str,
    anchor_table_name: str,
    lower_bound_time: str,
    cutoff_value: str,
    cursor_column_name: str,
    timestamp_column_name: str,
    cursor_column_type: str,
) -> tuple[str | None, bool]:
    row: CursorLowerBoundQueryRow | None = client.query_one(
        statement="SELECT min(" + cursor_column_name + ") AS lower_bound_cursor "
        f"FROM {database}.{anchor_table_name} "
        f"WHERE {timestamp_column_name} >= CAST('{lower_bound_time}' AS DateTime64(3)) "
        f"AND {cursor_column_name} <= "
        f"{_render_cast_literal(value=cutoff_value, column_type=cursor_column_type)}",
        decode=_decode_cursor_lower_bound_query_row,
    )
    if row is None or row.lower_bound_cursor is None:
        return None, True
    return row.lower_bound_cursor, False


def _external_source_replay_config_for_key(
    *, desired_state: DesiredState, key: ObjectKey
) -> ExternalSourceReplayConfig | None:
    external_source_replay_config: ExternalSourceReplayConfig
    for external_source_replay_config in desired_state.external_source_replay_configs:
        if external_source_replay_config.key == key:
            return external_source_replay_config
    return None


def _subtract_seconds_from_timestamp(*, timestamp_value: str, seconds: int) -> str:
    parsed_timestamp: datetime = datetime.strptime(timestamp_value, "%Y-%m-%d %H:%M:%S.%f")
    return (parsed_timestamp - timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _render_seeded_scalar_prefix_copy_statement(
    *,
    shadow_target_name: str,
    live_table_name: str,
    database: str,
    boundary_key: str,
    boundary_column_type: str,
    lower_bound_value: str,
    copyable_column_names: tuple[str, ...],
) -> str:
    column_list_sql: str = ", ".join(copyable_column_names)
    return (
        f"INSERT INTO {database}.{shadow_target_name} ({column_list_sql})\n"
        f"SELECT {column_list_sql}\n"
        f"FROM {database}.{live_table_name}\n"
        f"WHERE {boundary_key} < "
        f"{_render_cast_literal(value=lower_bound_value, column_type=boundary_column_type)}"
    )


def _load_scalar_boundary_column_type(
    *,
    client: ClickHouseClient,
    database: str,
    table_name: str,
    boundary_key: str,
    external_source_replay_config: ExternalSourceReplayConfig | None,
) -> str:
    physical_boundary_key: str = boundary_key
    if external_source_replay_config is not None:
        if boundary_key == REPLAY_CURSOR_COLUMN_NAME:
            physical_boundary_key = external_source_replay_config.cursor_column_name or boundary_key
        elif boundary_key == REPLAY_TIMESTAMP_COLUMN_NAME:
            physical_boundary_key = (
                external_source_replay_config.timestamp_column_name or boundary_key
            )
        elif boundary_key == REPLAY_LANDED_AT_COLUMN_NAME:
            physical_boundary_key = (
                external_source_replay_config.landed_at_column_name or boundary_key
            )
    row: TableColumnSystemRow | None = client.query_one(
        statement="SELECT name, type FROM system.columns "
        f"WHERE database = '{database}' AND table = '{table_name}' "
        f"AND name = '{physical_boundary_key}'",
        decode=_decode_table_column_system_row,
    )
    if row is None:
        raise BackfillExecutionError(
            "Could not resolve boundary column type for '"
            f"{physical_boundary_key}' on {database}.{table_name}"
        )
    return row.type


def _render_cast_literal(*, value: str, column_type: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"CAST('{escaped_value}' AS {column_type})"


def _render_seeded_offset_prefix_copy_statement(
    *,
    shadow_target_name: str,
    live_table_name: str,
    database: str,
    lower_bound_rows: tuple[ActiveOffsetFrontierQueryRow, ...],
    copyable_column_names: tuple[str, ...],
) -> str:
    lower_bound_select_rows: list[str] = []
    lower_bound_row: ActiveOffsetFrontierQueryRow
    for lower_bound_row in lower_bound_rows:
        lower_bound_select_rows.append(
            "SELECT "
            f"{lower_bound_row._replay_partition} AS {REPLAY_PARTITION_COLUMN_NAME}, "
            f"{lower_bound_row.cutoff_offset} AS start_offset"
        )
    column_list_sql: str = ", ".join(copyable_column_names)
    selected_column_list_sql: str = ", ".join(f"active.{name}" for name in copyable_column_names)
    return (
        f"INSERT INTO {database}.{shadow_target_name} ({column_list_sql})\n"
        "WITH active_start_offsets AS (\n" + "\nUNION ALL\n".join(lower_bound_select_rows) + "\n)\n"
        f"SELECT {selected_column_list_sql}\n"
        f"FROM {database}.{live_table_name} AS active\n"
        "INNER JOIN active_start_offsets\n"
        + "ON active."
        + REPLAY_PARTITION_COLUMN_NAME
        + " = active_start_offsets."
        + REPLAY_PARTITION_COLUMN_NAME
        + "\n"
        f"WHERE active.{REPLAY_OFFSET_COLUMN_NAME} < active_start_offsets.start_offset"
    )


def _decode_table_column_system_row(row: Mapping[str, object]) -> TableColumnSystemRow:
    return TableColumnSystemRow(name=str(row["name"]), type=str(row["type"]))


def _decode_active_scalar_frontier_query_row(
    row: Mapping[str, object],
) -> ActiveScalarFrontierQueryRow:
    return ActiveScalarFrontierQueryRow(
        cutoff_value=None if row["cutoff_value"] is None else str(row["cutoff_value"])
    )


def _decode_cursor_lower_bound_query_row(
    row: Mapping[str, object],
) -> CursorLowerBoundQueryRow:
    return CursorLowerBoundQueryRow(
        lower_bound_cursor=(
            None if row["lower_bound_cursor"] is None else str(row["lower_bound_cursor"])
        )
    )


def _decode_active_offset_frontier_query_row(
    row: Mapping[str, object],
) -> ActiveOffsetFrontierQueryRow:
    return ActiveOffsetFrontierQueryRow(
        _replay_partition=row[REPLAY_PARTITION_COLUMN_NAME],
        cutoff_offset=str(row["cutoff_offset"]),
    )
