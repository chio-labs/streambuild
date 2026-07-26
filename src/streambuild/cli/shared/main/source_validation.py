from __future__ import annotations

from collections.abc import Mapping

from streambuild.cli.shared.exceptions import CliUserError
from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledPipeline,
    ExternalSourceReplayConfig,
)
from streambuild.compiler.shared.constants import (
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient


def validate_declared_external_sources(
    *,
    client: ClickHouseClient,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    database: str,
) -> None:
    source_step: CompiledExternalSource
    for source_step in (
        compiled_pipeline.source
        for compiled_pipeline in compiled_pipelines
        if isinstance(compiled_pipeline.source, CompiledExternalSource)
    ):
        external_source_replay_config: ExternalSourceReplayConfig = (
            _build_external_source_replay_config(source_step)
        )
        column_types_by_name: dict[str, str] = _load_source_column_types(
            client=client,
            database=database,
            table_name=external_source_replay_config.table_name,
        )
        if not column_types_by_name:
            raise CliUserError(
                "Adopted source table '"
                f"{external_source_replay_config.table_name}"
                "' does not exist in "
                f"database '{database}'"
            )
        _validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.partition_column_name,
            column_role="partition",
            require_datetime=False,
        )
        _validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.offset_column_name,
            column_role="offset",
            require_datetime=False,
        )
        _validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.timestamp_column_name,
            column_role="timestamp",
            require_datetime=True,
        )
        _validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.landed_at_column_name,
            column_role="landed_at",
            require_datetime=True,
        )
        _validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.cursor_column_name,
            column_role="cursor",
            require_datetime=False,
        )
        _validate_injected_alias_collisions(
            column_types_by_name=column_types_by_name,
            external_source_replay_config=external_source_replay_config,
        )


def _build_external_source_replay_config(
    source_step: CompiledExternalSource,
) -> ExternalSourceReplayConfig:
    return ExternalSourceReplayConfig(
        key=source_step.source_key,
        table_name=source_step.source.table_name,
        source_kind=source_step.source.kind,
        replay_boundary_mode=source_step.source.replay_boundary.mode,
        partition_column_name=source_step.source.replay_boundary.columns.partition,
        offset_column_name=source_step.source.replay_boundary.columns.offset,
        timestamp_column_name=source_step.source.replay_boundary.columns.timestamp,
        landed_at_column_name=source_step.source.replay_boundary.columns.landed_at,
        cursor_column_name=source_step.source.replay_boundary.columns.cursor,
    )


def _validate_injected_alias_collisions(
    *,
    column_types_by_name: dict[str, str],
    external_source_replay_config: ExternalSourceReplayConfig,
) -> None:
    alias_mappings: tuple[tuple[str, str | None], ...] = (
        (REPLAY_PARTITION_COLUMN_NAME, external_source_replay_config.partition_column_name),
        (REPLAY_OFFSET_COLUMN_NAME, external_source_replay_config.offset_column_name),
        (REPLAY_TIMESTAMP_COLUMN_NAME, external_source_replay_config.timestamp_column_name),
        (REPLAY_LANDED_AT_COLUMN_NAME, external_source_replay_config.landed_at_column_name),
        (REPLAY_CURSOR_COLUMN_NAME, external_source_replay_config.cursor_column_name),
    )
    alias_name: str
    physical_name: str | None
    for alias_name, physical_name in alias_mappings:
        if physical_name is None or alias_name == physical_name:
            continue
        if alias_name in column_types_by_name:
            raise CliUserError(
                "Adopted source table '"
                f"{external_source_replay_config.table_name}"
                "' already defines column '"
                f"{alias_name}"
                "', which conflicts with the injected replay alias for source column '"
                f"{physical_name}'"
            )


def _load_source_column_types(
    *,
    client: ClickHouseClient,
    database: str,
    table_name: str,
) -> dict[str, str]:
    rows: tuple[SourceColumnSystemRow, ...] = client.query_many(
        statement="SELECT name, type FROM system.columns "
        f"WHERE database = '{database}' AND table = '{table_name}'",
        decode=_decode_source_column_system_row,
    )
    return {row.name: row.type for row in rows}


def _validate_declared_column(
    *,
    column_types_by_name: dict[str, str],
    table_name: str,
    column_name: str | None,
    column_role: str,
    require_datetime: bool,
) -> None:
    if column_name is None:
        return
    column_type: str | None = column_types_by_name.get(column_name)
    if column_type is None:
        raise CliUserError(
            f"Adopted source table '{table_name}' is missing declared {column_role} column "
            f"'{column_name}'"
        )
    if require_datetime and "datetime" not in column_type.lower():
        raise CliUserError(
            f"Adopted source table '{table_name}' declares {column_role} column '{column_name}' "
            f"with incompatible type '{column_type}'"
        )


class SourceColumnSystemRow:
    def __init__(self, *, name: str, type: str) -> None:
        self.name = name
        self.type = type


def _decode_source_column_system_row(row: Mapping[str, object]) -> SourceColumnSystemRow:
    return SourceColumnSystemRow(name=str(row["name"]), type=str(row["type"]))
