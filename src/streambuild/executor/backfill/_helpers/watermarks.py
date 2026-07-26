"""Watermark resolution and persistence helpers for staged backfill."""

from collections.abc import Mapping

from streambuild.clickhouse.metadata_state.main.build_metadata_state_insert_statements import (
    build_metadata_state_insert_statements,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement
from streambuild.compiler.compile.models import DesiredState, ExternalSourceReplayConfig
from streambuild.compiler.metadata_state.main.build_metadata_state import build_metadata_state
from streambuild.compiler.metadata_state.models import DeploymentWatermarkRecord, MetadataState
from streambuild.compiler.planner.models import DeploymentPlan, RebuildSubtree
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    RAW_TABLE_NAME_PREFIX,
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.shared.models import (
    DesiredTable,
    ObjectKey,
)
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.backfill.models import OffsetWatermarkQueryRow
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.spec.types import ReplayLineageMode


def resolve_scalar_watermarks(
    *,
    deployment_id: str,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    replay_lineage_mode: ReplayLineageMode | str,
    boundary_time: str,
) -> tuple[DeploymentWatermarkRecord, ...]:
    """Resolve scalar replay cutoffs for timestamp-based replay modes."""

    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    boundary_key_by_root: dict[ObjectKey, str] = {
        subtree.root_key: _scalar_boundary_key(
            desired_state=desired_state,
            anchor_key=subtree.upstream_boundary_key,
            replay_lineage_mode=resolved_replay_lineage_mode,
        )
        for subtree in deployment_plan.rebuild_subtrees
    }
    return tuple(
        DeploymentWatermarkRecord(
            deployment_id=deployment_id,
            root_key=subtree.root_key,
            anchor_key=subtree.upstream_boundary_key,
            boundary_key=boundary_key_by_root[subtree.root_key],
            cutoff_value=boundary_time,
        )
        for subtree in deployment_plan.rebuild_subtrees
    )


def resolve_cursor_watermarks(
    *,
    client: ClickHouseClient,
    deployment_id: str,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    default_database: str,
) -> tuple[DeploymentWatermarkRecord, ...]:
    """Resolve cursor replay cutoffs from the current max cursor value."""

    deployment_watermarks: list[DeploymentWatermarkRecord] = []
    subtree: RebuildSubtree
    for subtree in deployment_plan.rebuild_subtrees:
        database: str = subtree.root_key.database or default_database
        external_source_replay_config: ExternalSourceReplayConfig | None = (
            _external_source_replay_config_for_key(
                desired_state=desired_state,
                key=subtree.upstream_boundary_key,
            )
        )
        cursor_column_name: str = (
            external_source_replay_config.cursor_column_name
            if external_source_replay_config is not None
            and external_source_replay_config.cursor_column_name is not None
            else REPLAY_CURSOR_COLUMN_NAME
        )
        anchor_table_name: str = _landing_table_name_for_anchor(
            desired_state=desired_state,
            anchor_key=subtree.upstream_boundary_key,
        )
        cutoff_value: str = _load_cursor_cutoff_value(
            client=client,
            database=database,
            table_name=anchor_table_name,
            cursor_column_name=cursor_column_name,
        )
        deployment_watermarks.append(
            DeploymentWatermarkRecord(
                deployment_id=deployment_id,
                root_key=subtree.root_key,
                anchor_key=subtree.upstream_boundary_key,
                boundary_key=REPLAY_CURSOR_COLUMN_NAME,
                cutoff_value=cutoff_value,
            )
        )
    return tuple(deployment_watermarks)


def resolve_offset_watermarks(
    *,
    client: ClickHouseClient,
    deployment_id: str,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    default_database: str,
    boundary_time: str,
) -> tuple[DeploymentWatermarkRecord, ...]:
    """Resolve per-partition offset cutoffs from the landing/raw table at the boundary."""

    physical_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name
        for prepared in deployment_plan.prepared_shadow_objects
    }
    landing_table_name_by_root: dict[ObjectKey, str] = {
        subtree.root_key: _staged_table_name_if_present(
            logical_table_name=_landing_table_name_for_anchor(
                desired_state=desired_state,
                anchor_key=subtree.upstream_boundary_key,
            ),
            physical_name_by_key=physical_name_by_key,
        )
        for subtree in deployment_plan.rebuild_subtrees
    }
    deployment_watermarks: list[DeploymentWatermarkRecord] = []
    subtree: RebuildSubtree
    for subtree in deployment_plan.rebuild_subtrees:
        landing_table_name: str = landing_table_name_by_root[subtree.root_key]
        database: str = subtree.root_key.database or default_database
        external_source_replay_config: ExternalSourceReplayConfig | None = (
            _external_source_replay_config_for_key(
                desired_state=desired_state,
                key=subtree.upstream_boundary_key,
            )
        )
        rows: tuple[OffsetWatermarkQueryRow, ...] = client.query_many(
            statement=_render_offset_cutoff_query(
                database=database,
                landing_table_name=landing_table_name,
                boundary_time=boundary_time,
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
            ),
            decode=_decode_offset_watermark_query_row,
        )
        row: OffsetWatermarkQueryRow
        for row in rows:
            deployment_watermarks.append(
                DeploymentWatermarkRecord(
                    deployment_id=deployment_id,
                    root_key=subtree.root_key,
                    anchor_key=subtree.upstream_boundary_key,
                    boundary_key=f"{REPLAY_PARTITION_COLUMN_NAME}={row._replay_partition}",
                    cutoff_value=row.cutoff_offset,
                )
            )

    return tuple(deployment_watermarks)


def _staged_table_name_if_present(
    *,
    logical_table_name: str,
    physical_name_by_key: dict[ObjectKey, str],
) -> str:
    key: ObjectKey
    physical_name: str
    for key, physical_name in physical_name_by_key.items():
        if key.object_type == DESIRED_OBJECT_TYPE_TABLE and key.name == logical_table_name:
            return physical_name
    return logical_table_name


def persist_deployment_watermarks(
    *,
    client: ClickHouseClient,
    metadata_database: str,
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...],
) -> None:
    """Persist resolved deployment watermark rows."""

    metadata_state: MetadataState = build_metadata_state(
        object_states=(),
        deployments=(),
        deployment_watermarks=deployment_watermarks,
        deployment_runtime_details=(),
        publish_events=(),
    )
    insert_statements: tuple[RenderedClickHouseStatement, ...] = (
        build_metadata_state_insert_statements(
            database=metadata_database,
            object_states=metadata_state.object_states,
            deployments=metadata_state.deployments,
            deployment_watermarks=metadata_state.deployment_watermarks,
            deployment_runtime_details=metadata_state.deployment_runtime_details,
            publish_events=metadata_state.publish_events,
        )
    )
    statement: RenderedClickHouseStatement
    for statement in insert_statements:
        if not statement.rows:
            continue
        client.insert_rows(table=_insert_table_name(statement.sql), rows=statement.rows)


def _scalar_boundary_key(
    *,
    desired_state: DesiredState,
    anchor_key: ObjectKey,
    replay_lineage_mode: ReplayLineageMode,
) -> str:
    external_source_replay_config: ExternalSourceReplayConfig | None = (
        _external_source_replay_config_for_key(
            desired_state=desired_state,
            key=anchor_key,
        )
    )
    if external_source_replay_config is not None:
        if replay_lineage_mode == ReplayLineageMode.CURSOR:
            if external_source_replay_config.cursor_column_name is None:
                raise BackfillExecutionError(
                    "Source table '"
                    f"{external_source_replay_config.table_name}"
                    "' does not declare a cursor replay boundary column"
                )
            return REPLAY_CURSOR_COLUMN_NAME
        if replay_lineage_mode == ReplayLineageMode.TIMESTAMP:
            if external_source_replay_config.timestamp_column_name is None:
                raise BackfillExecutionError(
                    "Source table '"
                    f"{external_source_replay_config.table_name}"
                    "' does not declare a timestamp "
                    "replay boundary column"
                )
            return REPLAY_TIMESTAMP_COLUMN_NAME
        if external_source_replay_config.landed_at_column_name is not None:
            return REPLAY_LANDED_AT_COLUMN_NAME
        if external_source_replay_config.timestamp_column_name is not None:
            return REPLAY_TIMESTAMP_COLUMN_NAME
        raise BackfillExecutionError(
            "Source table '"
            f"{external_source_replay_config.table_name}"
            "' does not declare a scalar replay "
            "boundary column"
        )
    desired_anchor: DesiredTable = next(
        object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable) and object_.key == anchor_key
    )
    if replay_lineage_mode == ReplayLineageMode.TIMESTAMP:
        return REPLAY_TIMESTAMP_COLUMN_NAME
    if replay_lineage_mode == ReplayLineageMode.CURSOR:
        return REPLAY_CURSOR_COLUMN_NAME
    anchor_column_names: set[str] = {column.name for column in desired_anchor.columns}
    if REPLAY_LANDED_AT_COLUMN_NAME in anchor_column_names:
        return REPLAY_LANDED_AT_COLUMN_NAME
    if {REPLAY_PARTITION_COLUMN_NAME, REPLAY_OFFSET_COLUMN_NAME}.issubset(anchor_column_names):
        return REPLAY_LANDED_AT_COLUMN_NAME
    return REPLAY_LANDED_AT_COLUMN_NAME


def _landing_table_name_for_anchor(
    *,
    desired_state: DesiredState,
    anchor_key: ObjectKey,
) -> str:
    external_source_replay_config: ExternalSourceReplayConfig | None = (
        _external_source_replay_config_for_key(
            desired_state=desired_state,
            key=anchor_key,
        )
    )
    if external_source_replay_config is not None:
        return external_source_replay_config.table_name
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
    partition_column_name: str = REPLAY_PARTITION_COLUMN_NAME,
    offset_column_name: str = REPLAY_OFFSET_COLUMN_NAME,
    boundary_time_column_name: str = REPLAY_LANDED_AT_COLUMN_NAME,
) -> str:
    select_sql: str = (
        f"SELECT {partition_column_name} AS {REPLAY_PARTITION_COLUMN_NAME}, "
        f"max({offset_column_name}) AS cutoff_offset\n"
    )
    return (
        select_sql + f"FROM {database}.{landing_table_name}\n"
        f"WHERE {boundary_time_column_name} <= CAST('{boundary_time}' AS DateTime64(3))\n"
        f"GROUP BY {partition_column_name}\n"
        f"ORDER BY {partition_column_name}"
    )


def _load_cursor_cutoff_value(
    *,
    client: ClickHouseClient,
    database: str,
    table_name: str,
    cursor_column_name: str,
) -> str:
    row: OffsetWatermarkQueryRow | None = client.query_one(
        statement="SELECT coalesce(toString(max("
        f"{cursor_column_name}"
        ")), '') AS cutoff_offset "
        f"FROM {database}.{table_name}",
        decode=_decode_cursor_cutoff_query_row,
    )
    if row is None:
        return ""
    return row.cutoff_offset


def _external_source_replay_config_for_key(
    *, desired_state: DesiredState, key: ObjectKey
) -> ExternalSourceReplayConfig | None:
    external_source_replay_config: ExternalSourceReplayConfig
    for external_source_replay_config in desired_state.external_source_replay_configs:
        if external_source_replay_config.key == key:
            return external_source_replay_config
    return None


def _insert_table_name(statement_sql: str) -> str:
    statement_prefix: str = "INSERT INTO "
    remainder: str = statement_sql[len(statement_prefix) :]
    return remainder.split(" ", 1)[0]


def _decode_offset_watermark_query_row(row: Mapping[str, object]) -> OffsetWatermarkQueryRow:
    return OffsetWatermarkQueryRow(
        _replay_partition=row[REPLAY_PARTITION_COLUMN_NAME],
        cutoff_offset=str(row["cutoff_offset"]),
    )


def _decode_cursor_cutoff_query_row(row: Mapping[str, object]) -> OffsetWatermarkQueryRow:
    return OffsetWatermarkQueryRow(
        _replay_partition=0,
        cutoff_offset=str(row["cutoff_offset"]),
    )
