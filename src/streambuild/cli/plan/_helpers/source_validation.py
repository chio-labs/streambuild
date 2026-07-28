"""Adopted external source validation helpers."""

from __future__ import annotations

from streambuild.adapter.models import CatalogRelation, CatalogSnapshot
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.constants import (
    CLICKHOUSE_DATETIME_PREFIXES,
    CLICKHOUSE_DATETIME_TYPES,
    CLICKHOUSE_INTEGER_TYPES,
    CLICKHOUSE_SCALAR_TYPE_WRAPPERS,
)
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
    require_integer: bool,
) -> None:
    if column_name is None:
        return
    column_type: str | None = column_types_by_name.get(column_name)
    if column_type is None:
        raise CliUserError(
            f"Adopted source table '{table_name}' is missing declared {column_role} column "
            f"'{column_name}'"
        )
    normalized_type: str = _unwrap_scalar_type(column_type=column_type)
    if require_datetime and not _is_datetime_type(column_type=normalized_type):
        raise CliUserError(
            f"Adopted source table '{table_name}' declares {column_role} column '{column_name}' "
            f"with incompatible type '{column_type}'"
        )
    if require_integer and normalized_type not in CLICKHOUSE_INTEGER_TYPES:
        raise CliUserError(
            f"Adopted source table '{table_name}' declares {column_role} column '{column_name}' "
            f"with incompatible type '{column_type}'"
        )


def validate_external_source_mapping_consistency(
    *, external_source_replay_configs: tuple[ExternalSourceReplayConfig, ...]
) -> None:
    """Reject conflicting declarations for one adopted physical relation."""

    signature_by_table_name: dict[str, tuple[object, ...]] = {}
    config: ExternalSourceReplayConfig
    for config in external_source_replay_configs:
        signature: tuple[object, ...] = (
            config.replay_boundary_mode,
            config.partition_column_name,
            config.offset_column_name,
            config.timestamp_column_name,
            config.landed_at_column_name,
            config.cursor_column_name,
        )
        existing_signature: tuple[object, ...] | None = signature_by_table_name.get(
            config.table_name
        )
        if existing_signature is not None and existing_signature != signature:
            raise CliUserError(
                f"Adopted source table '{config.table_name}' has conflicting replay mappings"
            )
        signature_by_table_name[config.table_name] = signature


def _unwrap_scalar_type(*, column_type: str) -> str:
    normalized_type: str = column_type.replace(" ", "")
    wrapper: str
    for wrapper in CLICKHOUSE_SCALAR_TYPE_WRAPPERS:
        prefix: str = f"{wrapper}("
        if normalized_type.startswith(prefix) and normalized_type.endswith(")"):
            return _unwrap_scalar_type(column_type=normalized_type[len(prefix) : -1])
    return normalized_type


def _is_datetime_type(*, column_type: str) -> bool:
    return (
        column_type in CLICKHOUSE_DATETIME_TYPES
        or column_type.startswith(CLICKHOUSE_DATETIME_PREFIXES)
        and column_type.endswith(")")
    )
