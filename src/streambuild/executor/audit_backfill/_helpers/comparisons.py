"""Comparison helpers for audit backfill."""

import re
from collections.abc import Mapping
from typing import cast

from sqlglot import exp, parse_one

from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    MATERIALIZED_VIEW_NAME_PREFIX,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.shared.main.build_deployment_physical_name import (
    build_deployment_physical_name,
)
from streambuild.compiler.shared.models import ObjectKey
from streambuild.executor.audit_backfill.constants import ACCEPTABLE_LAG_SECONDS
from streambuild.executor.audit_backfill.exceptions import AuditBackfillExecutionError
from streambuild.executor.audit_backfill.models import (
    ColumnNameSystemRow,
    CountQueryRow,
    CreateTableQueryRow,
    OffsetCatchupSummary,
    OffsetSummaryQueryRow,
    RootAuditResult,
    ScalarCatchupSummary,
    ScalarSummaryQueryRow,
)
from streambuild.executor.audit_backfill.types import AuditAssessment
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.constants import (
    BLANK_VALUES,
)
from streambuild.spec.types import ReplayLineageMode


def build_root_audit_results(
    *,
    client: ClickHouseClient,
    default_database: str,
    deployment_id: str,
    inspected_state: InspectedManagedTableState,
) -> tuple[RootAuditResult, ...]:
    """Build audit comparisons for each rebuilt root target."""

    staged_name_by_root: dict[ObjectKey, str] = {
        ObjectKey(
            database=candidate.database,
            object_type=DESIRED_OBJECT_TYPE_TABLE,
            name=candidate.logical_name,
        ): candidate.physical_name
        for candidate in inspected_state.physical_candidates
        if candidate.logical_name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
        if candidate.physical_name
        == build_deployment_physical_name(
            logical_name=candidate.logical_name, deployment_id=deployment_id
        )
    }
    return tuple(
        _build_root_audit_result(
            client=client,
            default_database=default_database,
            root_key=root_key,
            staged_physical_name=staged_name_by_root[root_key],
            active_exists=_has_active_binding(inspected_state=inspected_state, root_key=root_key),
        )
        for root_key in tuple(
            sorted(
                staged_name_by_root,
                key=lambda value: (value.database or "", value.object_type, value.name),
            )
        )
    )


def _build_root_audit_result(
    *,
    client: ClickHouseClient,
    default_database: str,
    root_key: ObjectKey,
    staged_physical_name: str,
    active_exists: bool,
) -> RootAuditResult:
    database: str = root_key.database or default_database
    staged_exists: bool = _table_exists(
        client=client, database=database, table_name=staged_physical_name
    )
    staged_materialized_view_name: str = _build_staged_materialized_view_name(staged_physical_name)
    replay_source_name: str | None = None
    replay_source_row_count: int | None = None
    active_row_count: int | None = (
        _safe_row_count(client=client, database=database, table_name=root_key.name)
        if active_exists
        else None
    )
    staged_row_count: int | None = (
        _safe_row_count(client=client, database=database, table_name=staged_physical_name)
        if staged_exists
        else None
    )
    row_delta: int | None = None
    row_ratio: float | None = None
    if active_row_count is not None and staged_row_count is not None:
        row_delta = staged_row_count - active_row_count
        row_ratio = None if active_row_count == 0 else staged_row_count / active_row_count
    active_queryable: bool = active_exists and active_row_count is not None
    offset_summary: OffsetCatchupSummary | None = None
    scalar_summary: ScalarCatchupSummary | None = None
    replay_lineage_mode: ReplayLineageMode | None = _infer_replay_lineage_mode(
        client=client,
        database=database,
        table_name=staged_physical_name,
    )
    if staged_exists:
        replay_source_name = _resolve_staged_source_table_name(
            client=client,
            database=database,
            staged_materialized_view_name=staged_materialized_view_name,
        )
        replay_source_row_count = (
            None
            if replay_source_name is None
            else _safe_row_count(client=client, database=database, table_name=replay_source_name)
        )
    if staged_exists and replay_lineage_mode == ReplayLineageMode.OFFSETS:
        offset_summary = _offset_catchup_summary(
            client=client,
            database=database,
            active_table_name=root_key.name,
            staged_table_name=staged_physical_name,
            active_exists=active_queryable,
            staged_materialized_view_name=staged_materialized_view_name,
        )
    elif active_queryable and staged_exists and replay_lineage_mode is not None:
        scalar_summary = _scalar_catchup_summary(
            client=client,
            database=database,
            active_table_name=root_key.name,
            staged_table_name=staged_physical_name,
            replay_lineage_mode=replay_lineage_mode,
        )
    warnings: tuple[str, ...] = _build_root_warnings(
        root_key=root_key,
        active_exists=active_exists,
        active_row_count=active_row_count,
        staged_row_count=staged_row_count,
        row_ratio=row_ratio,
        replay_source_name=replay_source_name,
        replay_source_row_count=replay_source_row_count,
    )
    return RootAuditResult(
        root_key=root_key,
        staged_physical_name=staged_physical_name,
        state="active_view_present" if active_exists else "greenfield",
        replay_source_name=replay_source_name,
        replay_source_row_count=replay_source_row_count,
        staged_exists=staged_exists,
        active_exists=active_exists,
        active_row_count=active_row_count,
        staged_row_count=staged_row_count,
        row_delta=row_delta,
        row_ratio=row_ratio,
        assessment=_build_root_assessment(
            staged_exists=staged_exists,
            active_exists=active_exists,
            active_row_count=active_row_count,
            staged_row_count=staged_row_count,
            replay_source_row_count=replay_source_row_count,
            replay_lineage_mode=replay_lineage_mode,
            offset_summary=offset_summary,
            scalar_summary=scalar_summary,
        ),
        replay_lineage_mode=replay_lineage_mode,
        offset_catchup_summary=offset_summary,
        scalar_catchup_summary=scalar_summary,
        warnings=warnings,
    )


def _table_exists(*, client: ClickHouseClient, database: str, table_name: str) -> bool:
    row: CountQueryRow | None = client.query_one(
        statement="SELECT count() AS value FROM system.tables "
        f"WHERE database = '{database}' AND name = '{table_name}'",
        decode=_decode_count_query_row,
    )
    return bool(row.value) if row is not None else False


def _row_count(*, client: ClickHouseClient, database: str, table_name: str) -> int:
    row: CountQueryRow | None = client.query_one(
        statement=f"SELECT count() AS value FROM {database}.{table_name}",
        decode=_decode_count_query_row,
    )
    if row is None:
        raise AuditBackfillExecutionError(f"Expected row count for {database}.{table_name}")
    return row.value


def _safe_row_count(*, client: ClickHouseClient, database: str, table_name: str) -> int | None:
    try:
        return _row_count(client=client, database=database, table_name=table_name)
    except Exception:
        return None


def _has_active_binding(
    *,
    inspected_state: InspectedManagedTableState,
    root_key: ObjectKey,
) -> bool:
    return any(
        binding.database == (root_key.database or binding.database)
        and binding.logical_name == root_key.name
        for binding in inspected_state.active_bindings
    )


def _infer_replay_lineage_mode(
    *,
    client: ClickHouseClient,
    database: str,
    table_name: str,
) -> ReplayLineageMode | None:
    rows: tuple[ColumnNameSystemRow, ...] = client.query_many(
        statement=(
            f"SELECT name FROM system.columns "
            f"WHERE database = '{database}' AND table = '{table_name}'"
        ),
        decode=_decode_column_name_system_row,
    )
    column_names: set[str] = {row.name for row in rows}
    if {REPLAY_PARTITION_COLUMN_NAME, REPLAY_OFFSET_COLUMN_NAME}.issubset(column_names):
        return ReplayLineageMode(ReplayLineageMode.OFFSETS)
    if REPLAY_TIMESTAMP_COLUMN_NAME in column_names:
        return ReplayLineageMode(ReplayLineageMode.TIMESTAMP)
    if REPLAY_LANDED_AT_COLUMN_NAME in column_names:
        return ReplayLineageMode(ReplayLineageMode.LANDED_AT)
    return None


def _offset_catchup_summary(
    *,
    client: ClickHouseClient,
    database: str,
    active_table_name: str,
    staged_table_name: str,
    active_exists: bool,
    staged_materialized_view_name: str,
) -> OffsetCatchupSummary:
    active_offsets_sql: str
    if active_exists:
        active_offsets_sql = (
            "SELECT "
            + REPLAY_PARTITION_COLUMN_NAME
            + ", max("
            + REPLAY_OFFSET_COLUMN_NAME
            + ") AS max_offset "
            f"FROM {database}.{active_table_name} GROUP BY {REPLAY_PARTITION_COLUMN_NAME}"
        )
    else:
        active_offsets_sql = (
            f"SELECT toInt64(0) AS {REPLAY_PARTITION_COLUMN_NAME}, toInt64(0) AS max_offset WHERE 0"
        )
    staged_offsets_sql: str = (
        f"SELECT {REPLAY_PARTITION_COLUMN_NAME}, max({REPLAY_OFFSET_COLUMN_NAME}) AS max_offset "
        f"FROM {database}.{staged_table_name} GROUP BY {REPLAY_PARTITION_COLUMN_NAME}"
    )
    source_table_name: str | None = _resolve_staged_source_table_name(
        client=client,
        database=database,
        staged_materialized_view_name=staged_materialized_view_name,
    )
    boundary_column: str | None = (
        None
        if source_table_name is None
        else _resolve_offset_boundary_column(
            client=client,
            database=database,
            source_table_name=source_table_name,
        )
    )
    raw_offsets_sql: str | None = None
    staged_progress_sql: str | None = None
    if source_table_name is not None:
        raw_offsets_sql = (
            "SELECT "
            + REPLAY_PARTITION_COLUMN_NAME
            + ", max("
            + REPLAY_OFFSET_COLUMN_NAME
            + ") AS max_offset "
            f"FROM {database}.{source_table_name} GROUP BY {REPLAY_PARTITION_COLUMN_NAME}"
        )
    if source_table_name is not None and boundary_column is not None:
        staged_progress_sql = (
            f"SELECT source.{REPLAY_PARTITION_COLUMN_NAME}, "
            f"max(source.{boundary_column}) AS staged_max_boundary "
            f"FROM {database}.{source_table_name} AS source "
            f"INNER JOIN ({staged_offsets_sql}) AS staged_offsets "
            "ON source."
            + REPLAY_PARTITION_COLUMN_NAME
            + " = staged_offsets."
            + REPLAY_PARTITION_COLUMN_NAME
            + " "
            f"AND source.{REPLAY_OFFSET_COLUMN_NAME} = staged_offsets.max_offset "
            f"GROUP BY source.{REPLAY_PARTITION_COLUMN_NAME}"
        )
    row: OffsetSummaryQueryRow | None = client.query_one(
        statement=_build_offset_summary_query(
            active_offsets_sql=active_offsets_sql,
            staged_offsets_sql=staged_offsets_sql,
            raw_offsets_sql=raw_offsets_sql,
            staged_progress_sql=staged_progress_sql,
            database=database,
            source_table_name=source_table_name,
            boundary_column=boundary_column,
        ),
        decode=_decode_offset_summary_query_row,
    )
    if row is None:
        raise AuditBackfillExecutionError("Expected offset catchup summary row")
    return OffsetCatchupSummary(
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


def _scalar_catchup_summary(
    *,
    client: ClickHouseClient,
    database: str,
    active_table_name: str,
    staged_table_name: str,
    replay_lineage_mode: ReplayLineageMode,
) -> ScalarCatchupSummary:
    boundary_column: str = (
        REPLAY_TIMESTAMP_COLUMN_NAME
        if replay_lineage_mode == ReplayLineageMode.TIMESTAMP
        else REPLAY_LANDED_AT_COLUMN_NAME
    )
    scalar_query: str = (
        "SELECT "
        f"toString(min(active.{boundary_column})) AS active_min_value, "
        f"toString(max(active.{boundary_column})) AS active_max_value, "
        f"toString(min(staged.{boundary_column})) AS staged_min_value, "
        f"toString(max(staged.{boundary_column})) AS staged_max_value, "
        + "dateDiff('second', "
        + f"max(staged.{boundary_column}), max(active.{boundary_column})"
        + ") AS lag_seconds "
        f"FROM {database}.{active_table_name} AS active "
        f"CROSS JOIN {database}.{staged_table_name} AS staged"
    )
    row: ScalarSummaryQueryRow | None = client.query_one(
        statement=scalar_query,
        decode=_decode_scalar_summary_query_row,
    )
    if row is None:
        raise AuditBackfillExecutionError("Expected scalar catchup summary row")
    return ScalarCatchupSummary(
        active_min_value=row.active_min_value,
        active_max_value=row.active_max_value,
        staged_min_value=row.staged_min_value,
        staged_max_value=row.staged_max_value,
        lag_seconds=row.lag_seconds,
    )


def _build_root_assessment(
    *,
    staged_exists: bool,
    active_exists: bool,
    active_row_count: int | None,
    staged_row_count: int | None,
    replay_source_row_count: int | None,
    replay_lineage_mode: ReplayLineageMode | None,
    offset_summary: OffsetCatchupSummary | None,
    scalar_summary: ScalarCatchupSummary | None,
) -> AuditAssessment:
    if not staged_exists:
        return AuditAssessment(AuditAssessment.CAUTION)
    if staged_row_count == 0:
        if active_exists and active_row_count is not None and active_row_count > 0:
            return AuditAssessment(AuditAssessment.NOT_READY)
        return AuditAssessment(AuditAssessment.CAUTION)
    if not active_exists:
        return AuditAssessment(AuditAssessment.READY)
    if replay_lineage_mode == ReplayLineageMode.OFFSETS:
        if offset_summary is None:
            return AuditAssessment(AuditAssessment.CAUTION)
        if (
            active_exists
            and offset_summary.partitions_compared < offset_summary.active_partition_count
        ):
            return AuditAssessment(AuditAssessment.CAUTION)
        if active_exists and offset_summary.missing_staged_partition_count > 0:
            return AuditAssessment(AuditAssessment.CAUTION)
        if offset_summary.missing_freshness_partition_count > 0:
            return AuditAssessment(AuditAssessment.CAUTION)
        if offset_summary.lag_boundary_column is None or offset_summary.max_lag_seconds is None:
            return AuditAssessment(AuditAssessment.CAUTION)
        if offset_summary.max_lag_seconds <= ACCEPTABLE_LAG_SECONDS:
            if (
                active_row_count is not None
                and staged_row_count is not None
                and active_row_count > 0
                and staged_row_count < active_row_count * 0.5
            ):
                return AuditAssessment(AuditAssessment.CAUTION)
            return AuditAssessment(AuditAssessment.READY)
        return AuditAssessment(AuditAssessment.NOT_READY)
    if scalar_summary is None:
        return AuditAssessment(AuditAssessment.CAUTION)
    if scalar_summary.lag_seconds is None:
        return AuditAssessment(AuditAssessment.CAUTION)
    if scalar_summary.lag_seconds <= ACCEPTABLE_LAG_SECONDS:
        if (
            active_row_count is not None
            and staged_row_count is not None
            and active_row_count > 0
            and staged_row_count < active_row_count * 0.5
        ):
            return AuditAssessment(AuditAssessment.CAUTION)
        return AuditAssessment(AuditAssessment.READY)
    return AuditAssessment(AuditAssessment.NOT_READY)


def _build_root_warnings(
    *,
    root_key: ObjectKey,
    active_exists: bool,
    active_row_count: int | None,
    staged_row_count: int | None,
    row_ratio: float | None,
    replay_source_name: str | None,
    replay_source_row_count: int | None,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if replay_source_name is not None and replay_source_row_count == 0:
        warnings.append(f"replay source {replay_source_name} is empty")
    if (
        active_exists
        and active_row_count is not None
        and staged_row_count is not None
        and row_ratio is not None
        and row_ratio < 0.5
    ):
        warnings.append(f"staged row count is far below active row count for {root_key.name}")
    return tuple(warnings)


def _build_staged_materialized_view_name(staged_table_name: str) -> str:
    if not staged_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
        return staged_table_name
    return MATERIALIZED_VIEW_NAME_PREFIX + staged_table_name.removeprefix(
        TRANSFORM_TABLE_NAME_PREFIX
    )


def _resolve_staged_source_table_name(
    *,
    client: ClickHouseClient,
    database: str,
    staged_materialized_view_name: str,
) -> str | None:
    row: CreateTableQueryRow | None = client.query_one(
        statement="SELECT create_table_query FROM system.tables "
        f"WHERE database = '{database}' AND name = '{staged_materialized_view_name}'",
        decode=_decode_create_table_query_row,
    )
    if row is None:
        return None
    create_table_query: str = row.create_table_query
    query_match: re.Match[str] | None = re.search(
        r"\bAS\b\s*(SELECT.*)$",
        create_table_query,
        re.DOTALL,
    )
    if query_match is None:
        return None
    select_query: str = query_match.group(1)
    expression: exp.Expr = parse_one(select_query, dialect="clickhouse")
    source_table: exp.Table | None = next(expression.find_all(exp.Table), None)
    if source_table is None:
        return None
    return source_table.name


def _resolve_offset_boundary_column(
    *,
    client: ClickHouseClient,
    database: str,
    source_table_name: str,
) -> str | None:
    rows: tuple[ColumnNameSystemRow, ...] = client.query_many(
        statement="SELECT name FROM system.columns "
        f"WHERE database = '{database}' AND table = '{source_table_name}'",
        decode=_decode_column_name_system_row,
    )
    column_names: set[str] = {row.name for row in rows}
    if REPLAY_TIMESTAMP_COLUMN_NAME in column_names:
        return REPLAY_TIMESTAMP_COLUMN_NAME
    if REPLAY_LANDED_AT_COLUMN_NAME in column_names:
        return REPLAY_LANDED_AT_COLUMN_NAME
    return None


def _build_offset_summary_query(
    *,
    active_offsets_sql: str,
    staged_offsets_sql: str,
    raw_offsets_sql: str | None,
    staged_progress_sql: str | None,
    database: str,
    source_table_name: str | None,
    boundary_column: str | None,
) -> str:
    raw_offsets_cte: str = (
        "raw_offsets AS (" + raw_offsets_sql + "), "
        if raw_offsets_sql is not None
        else (
            "raw_offsets AS ("
            f"SELECT toInt64(0) AS {REPLAY_PARTITION_COLUMN_NAME}, toInt64(0) AS max_offset WHERE 0"
            "), "
        )
    )
    raw_latest_cte: str = (
        f"raw_latest AS (SELECT {REPLAY_PARTITION_COLUMN_NAME}, max("
        + boundary_column
        + ") AS raw_max_boundary FROM "
        + database
        + "."
        + source_table_name
        + f" GROUP BY {REPLAY_PARTITION_COLUMN_NAME}), "
        if source_table_name is not None and boundary_column is not None
        else (
            "raw_latest AS ("
            f"SELECT toInt64(0) AS {REPLAY_PARTITION_COLUMN_NAME}, "
            "CAST(NULL AS Nullable(DateTime64(3))) AS raw_max_boundary WHERE 0"
            "), "
        )
    )
    staged_progress_cte: str = (
        "staged_progress AS (" + staged_progress_sql + ") "
        if staged_progress_sql is not None
        else (
            "staged_progress AS ("
            f"SELECT toInt64(0) AS {REPLAY_PARTITION_COLUMN_NAME}, "
            "CAST(NULL AS Nullable(DateTime64(3))) AS staged_max_boundary WHERE 0"
            ") "
        )
    )
    return (
        f"WITH active_offsets AS ({active_offsets_sql}), "
        f"staged_offsets AS ({staged_offsets_sql}), "
        + raw_offsets_cte
        + raw_latest_cte
        + staged_progress_cte
        + "SELECT "
        + "(SELECT count() FROM active_offsets) AS active_partition_count, "
        + "(SELECT count() FROM staged_offsets) AS staged_partition_count, "
        + (
            "countIf(active_offsets.max_offset IS NOT NULL AND "
            "staged_offsets.max_offset IS NOT NULL) AS partitions_compared, "
        )
        + (
            "countIf(active_offsets.max_offset IS NOT NULL AND staged_offsets.max_offset IS NULL) "
            "AS missing_staged_partition_count, "
        )
        + (
            "countIf(staged_offsets.max_offset IS NOT NULL AND ("
            "staged_progress.staged_max_boundary IS NULL OR raw_latest.raw_max_boundary IS NULL)) "
            "AS missing_freshness_partition_count, "
        )
        + (
            "countIf(raw_offsets.max_offset > coalesce(staged_offsets.max_offset, -1)) "
            "AS lagging_partition_count, "
        )
        + (
            "max(greatest(raw_offsets.max_offset - "
            "coalesce(staged_offsets.max_offset, raw_offsets.max_offset), 0)) AS max_offset_gap, "
        )
        + (
            "avg(greatest(raw_offsets.max_offset - "
            "coalesce(staged_offsets.max_offset, raw_offsets.max_offset), 0)) "
            "AS average_offset_gap, "
        )
        + (
            "max(dateDiff('second', staged_progress.staged_max_boundary, "
            "raw_latest.raw_max_boundary)) AS max_lag_seconds, "
        )
        + (
            "avg(dateDiff('second', staged_progress.staged_max_boundary, "
            "raw_latest.raw_max_boundary)) AS average_lag_seconds "
        )
        + "FROM raw_offsets "
        + f"LEFT JOIN staged_offsets USING ({REPLAY_PARTITION_COLUMN_NAME}) "
        + f"LEFT JOIN active_offsets USING ({REPLAY_PARTITION_COLUMN_NAME}) "
        + f"LEFT JOIN raw_latest USING ({REPLAY_PARTITION_COLUMN_NAME}) "
        + f"LEFT JOIN staged_progress USING ({REPLAY_PARTITION_COLUMN_NAME})"
    )


def _decode_count_query_row(row: Mapping[str, object]) -> CountQueryRow:
    return CountQueryRow(value=int(cast(int, row["value"])))


def _decode_column_name_system_row(row: Mapping[str, object]) -> ColumnNameSystemRow:
    return ColumnNameSystemRow(name=str(row["name"]))


def _decode_offset_summary_query_row(row: Mapping[str, object]) -> OffsetSummaryQueryRow:
    return OffsetSummaryQueryRow(
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


def _decode_scalar_summary_query_row(row: Mapping[str, object]) -> ScalarSummaryQueryRow:
    return ScalarSummaryQueryRow(
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


def _decode_create_table_query_row(row: Mapping[str, object]) -> CreateTableQueryRow:
    return CreateTableQueryRow(create_table_query=str(row["create_table_query"]))
