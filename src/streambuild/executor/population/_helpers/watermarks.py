"""Resolve inclusive source-derived watermarks for shared population."""

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    RAW_TABLE_NAME_PREFIX,
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.compile.models import (
    DesiredState,
    DesiredTable,
    ExternalSourceReplayConfig,
    ObjectKey,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.executor.population.exceptions import PopulationExecutionError
from streambuild.executor.population.models import (
    OffsetWatermarkQueryRow,
    PopulationPlan,
    PopulationRoot,
    PopulationWatermark,
)


def resolve_population_watermarks(
    *,
    client: AdapterConnection,
    plan: PopulationPlan,
    desired_state: DesiredState,
    default_database: str,
    boundary_time: str,
) -> tuple[PopulationWatermark, ...]:
    """Resolve every root's inclusive cutoff through one implementation."""

    watermarks: list[PopulationWatermark] = []
    root: PopulationRoot
    for root in plan.roots:
        mode: ReplayLineageMode = ReplayLineageMode(root.replay_lineage_mode)
        if mode == ReplayLineageMode.OFFSETS:
            watermarks.extend(
                _offset_watermarks(
                    client=client,
                    root=root,
                    plan=plan,
                    desired_state=desired_state,
                    default_database=default_database,
                    boundary_time=boundary_time,
                )
            )
        elif mode == ReplayLineageMode.CURSOR:
            watermarks.append(
                _cursor_watermark(
                    client=client,
                    root=root,
                    desired_state=desired_state,
                    default_database=default_database,
                )
            )
        else:
            watermarks.append(
                _scalar_watermark(
                    root=root,
                    desired_state=desired_state,
                    mode=mode,
                    boundary_time=boundary_time,
                )
            )
    return tuple(watermarks)


def _scalar_watermark(
    *,
    root: PopulationRoot,
    desired_state: DesiredState,
    mode: ReplayLineageMode,
    boundary_time: str,
) -> PopulationWatermark:
    return PopulationWatermark(
        root_key=root.root_key,
        anchor_key=root.upstream_boundary_key,
        boundary_key=_scalar_boundary_key(
            desired_state=desired_state,
            anchor_key=root.upstream_boundary_key,
            replay_lineage_mode=mode,
        ),
        cutoff_value=boundary_time,
    )


def _cursor_watermark(
    *,
    client: AdapterConnection,
    root: PopulationRoot,
    desired_state: DesiredState,
    default_database: str,
) -> PopulationWatermark:
    external_config: ExternalSourceReplayConfig | None = _external_source_config(
        desired_state=desired_state, key=root.upstream_boundary_key
    )
    cursor_column_name: str = (
        external_config.cursor_column_name
        if external_config is not None and external_config.cursor_column_name is not None
        else REPLAY_CURSOR_COLUMN_NAME
    )
    anchor_table_name: str = _landing_table_name_for_anchor(
        desired_state=desired_state, anchor_key=root.upstream_boundary_key
    )
    row: OffsetWatermarkQueryRow | None = client.query_one(
        statement=(
            f"SELECT coalesce(toString(max({cursor_column_name})), '') AS cutoff_offset "
            f"FROM {root.root_key.database or default_database}.{anchor_table_name}"
        ),
        decode=_decode_cursor_cutoff_query_row,
    )
    return PopulationWatermark(
        root_key=root.root_key,
        anchor_key=root.upstream_boundary_key,
        boundary_key=REPLAY_CURSOR_COLUMN_NAME,
        cutoff_value="" if row is None else row.cutoff_offset,
    )


def _offset_watermarks(
    *,
    client: AdapterConnection,
    root: PopulationRoot,
    plan: PopulationPlan,
    desired_state: DesiredState,
    default_database: str,
    boundary_time: str,
) -> tuple[PopulationWatermark, ...]:
    physical_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name for prepared in plan.objects
    }
    landing_table_name: str = _staged_table_name_if_present(
        logical_table_name=_landing_table_name_for_anchor(
            desired_state=desired_state, anchor_key=root.upstream_boundary_key
        ),
        physical_name_by_key=physical_name_by_key,
    )
    external_config: ExternalSourceReplayConfig | None = _external_source_config(
        desired_state=desired_state, key=root.upstream_boundary_key
    )
    rows: tuple[OffsetWatermarkQueryRow, ...] = client.query_many(
        statement=_render_offset_cutoff_query(
            database=root.root_key.database or default_database,
            landing_table_name=landing_table_name,
            boundary_time=boundary_time,
            partition_column_name=(
                external_config.partition_column_name
                if external_config is not None and external_config.partition_column_name is not None
                else REPLAY_PARTITION_COLUMN_NAME
            ),
            offset_column_name=(
                external_config.offset_column_name
                if external_config is not None and external_config.offset_column_name is not None
                else REPLAY_OFFSET_COLUMN_NAME
            ),
            boundary_time_column_name=(
                external_config.landed_at_column_name
                if external_config is not None and external_config.landed_at_column_name is not None
                else (
                    external_config.timestamp_column_name
                    if external_config is not None
                    and external_config.timestamp_column_name is not None
                    else REPLAY_LANDED_AT_COLUMN_NAME
                )
            ),
        ),
        decode=_decode_offset_watermark_query_row,
    )
    return tuple(
        PopulationWatermark(
            root_key=root.root_key,
            anchor_key=root.upstream_boundary_key,
            boundary_key=f"{REPLAY_PARTITION_COLUMN_NAME}={row._replay_partition}",
            cutoff_value=row.cutoff_offset,
        )
        for row in rows
    )


def _staged_table_name_if_present(
    *, logical_table_name: str, physical_name_by_key: dict[ObjectKey, str]
) -> str:
    key: ObjectKey
    physical_name: str
    for key, physical_name in physical_name_by_key.items():
        if key.object_type == DESIRED_OBJECT_TYPE_TABLE and key.name == logical_table_name:
            return physical_name
    return logical_table_name


def _scalar_boundary_key(
    *,
    desired_state: DesiredState,
    anchor_key: ObjectKey,
    replay_lineage_mode: ReplayLineageMode,
) -> str:
    external_config: ExternalSourceReplayConfig | None = _external_source_config(
        desired_state=desired_state, key=anchor_key
    )
    if external_config is not None:
        if replay_lineage_mode == ReplayLineageMode.CURSOR:
            if external_config.cursor_column_name is None:
                raise PopulationExecutionError(
                    f"Source table '{external_config.table_name}' does not declare a cursor "
                    "replay boundary column"
                )
            return REPLAY_CURSOR_COLUMN_NAME
        if replay_lineage_mode == ReplayLineageMode.TIMESTAMP:
            if external_config.timestamp_column_name is None:
                raise PopulationExecutionError(
                    f"Source table '{external_config.table_name}' does not declare a timestamp "
                    "replay boundary column"
                )
            return REPLAY_TIMESTAMP_COLUMN_NAME
        if external_config.landed_at_column_name is not None:
            return REPLAY_LANDED_AT_COLUMN_NAME
        if external_config.timestamp_column_name is not None:
            return REPLAY_TIMESTAMP_COLUMN_NAME
        raise PopulationExecutionError(
            f"Source table '{external_config.table_name}' does not declare a scalar replay "
            "boundary column"
        )
    if replay_lineage_mode == ReplayLineageMode.TIMESTAMP:
        return REPLAY_TIMESTAMP_COLUMN_NAME
    if replay_lineage_mode == ReplayLineageMode.CURSOR:
        return REPLAY_CURSOR_COLUMN_NAME
    return REPLAY_LANDED_AT_COLUMN_NAME


def _landing_table_name_for_anchor(*, desired_state: DesiredState, anchor_key: ObjectKey) -> str:
    external_config: ExternalSourceReplayConfig | None = _external_source_config(
        desired_state=desired_state, key=anchor_key
    )
    if external_config is not None:
        return external_config.table_name
    desired_anchor: DesiredTable = next(
        object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable) and object_.key == anchor_key
    )
    if desired_anchor.name.startswith(RAW_TABLE_NAME_PREFIX):
        return desired_anchor.name
    current_key: ObjectKey = anchor_key
    desired_table_by_key: dict[ObjectKey, DesiredTable] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
    }
    while True:
        current_table: DesiredTable = desired_table_by_key[current_key]
        parent_key: ObjectKey = current_table.deps[0]
        if parent_key.name.startswith(RAW_TABLE_NAME_PREFIX):
            return parent_key.name
        current_key = parent_key


def _render_offset_cutoff_query(
    *,
    database: str,
    landing_table_name: str,
    boundary_time: str,
    partition_column_name: str,
    offset_column_name: str,
    boundary_time_column_name: str,
) -> str:
    return (
        f"SELECT {partition_column_name} AS {REPLAY_PARTITION_COLUMN_NAME}, "
        f"max({offset_column_name}) AS cutoff_offset\n"
        f"FROM {database}.{landing_table_name}\n"
        f"WHERE {boundary_time_column_name} <= CAST('{boundary_time}' AS DateTime64(3))\n"
        f"GROUP BY {partition_column_name}\n"
        f"ORDER BY {partition_column_name}"
    )


def _external_source_config(
    *, desired_state: DesiredState, key: ObjectKey
) -> ExternalSourceReplayConfig | None:
    config: ExternalSourceReplayConfig
    for config in desired_state.external_source_replay_configs:
        if config.key == key:
            return config
    return None


def _decode_offset_watermark_query_row(row: Mapping[str, object]) -> OffsetWatermarkQueryRow:
    return OffsetWatermarkQueryRow(
        _replay_partition=row[REPLAY_PARTITION_COLUMN_NAME],
        cutoff_offset=str(row["cutoff_offset"]),
    )


def _decode_cursor_cutoff_query_row(row: Mapping[str, object]) -> OffsetWatermarkQueryRow:
    return OffsetWatermarkQueryRow(_replay_partition=0, cutoff_offset=str(row["cutoff_offset"]))
