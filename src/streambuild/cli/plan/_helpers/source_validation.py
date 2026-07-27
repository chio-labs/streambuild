"""Adopted external source validation helpers."""

from __future__ import annotations

from streambuild.adapter.models import CatalogRelation, CatalogSnapshot
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.constants import DATETIME_TYPE_MARKER
from streambuild.compiler.compile.constants import (
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.compile.models import ExternalSourceReplayConfig


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
    catalog: CatalogSnapshot,
    table_name: str,
) -> dict[str, str]:
    relation: CatalogRelation | None = catalog.relation(table_name)
    if relation is None:
        return {}
    return {column.name: column.type for column in relation.columns}


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
