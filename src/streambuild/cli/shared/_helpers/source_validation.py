"""Adopted external source validation helpers."""

from __future__ import annotations

from collections.abc import Mapping

from streambuild.cli.shared.constants import DATETIME_TYPE_MARKER
from streambuild.cli.shared.exceptions import CliUserError
from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    ExternalSourceReplayConfig,
)
from streambuild.compiler.shared.constants import (
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def build_external_source_replay_config(
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


def validate_injected_alias_collisions(
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


def load_source_column_types(
    *,
    client: ClickHouseClient,
    database: str,
    table_name: str,
) -> dict[str, str]:
    rows: tuple[_SourceColumnSystemRow, ...] = client.query_many(
        statement="SELECT name, type FROM system.columns "
        f"WHERE database = '{database}' AND table = '{table_name}'",
        decode=decode_source_column_system_row,
    )
    return {row.name: row.type for row in rows}


def validate_declared_column(
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
    if require_datetime and DATETIME_TYPE_MARKER not in column_type.lower():
        raise CliUserError(
            f"Adopted source table '{table_name}' declares {column_role} column '{column_name}' "
            f"with incompatible type '{column_type}'"
        )


class _SourceColumnSystemRow:
    def __init__(self, *, name: str, type: str) -> None:
        self.name = name
        self.type = type


def decode_source_column_system_row(row: Mapping[str, object]) -> _SourceColumnSystemRow:
    return _SourceColumnSystemRow(name=str(row["name"]), type=str(row["type"]))
