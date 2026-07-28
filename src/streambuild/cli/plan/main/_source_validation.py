from __future__ import annotations

from streambuild.adapter.models import CatalogSnapshot
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan._helpers.source_validation import (
    load_source_column_types,
    validate_declared_column,
    validate_external_source_mapping_consistency,
    validate_injected_alias_collisions,
)
from streambuild.compiler.compile.models import ExternalSourceReplayConfig


def validate_declared_external_sources(
    *,
    catalog: CatalogSnapshot,
    external_source_replay_configs: tuple[ExternalSourceReplayConfig, ...],
    database: str,
) -> None:
    validate_external_source_mapping_consistency(
        external_source_replay_configs=external_source_replay_configs
    )
    external_source_replay_config: ExternalSourceReplayConfig
    for external_source_replay_config in external_source_replay_configs:
        column_types_by_name: dict[str, str] = load_source_column_types(
            catalog=catalog,
            table_name=external_source_replay_config.table_name,
        )
        if not column_types_by_name:
            raise CliUserError(
                "Adopted source table '"
                f"{external_source_replay_config.table_name}"
                "' does not exist in "
                f"database '{database}'"
            )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.partition_column_name,
            column_role="partition",
            require_datetime=False,
            require_integer=True,
        )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.offset_column_name,
            column_role="offset",
            require_datetime=False,
            require_integer=True,
        )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.timestamp_column_name,
            column_role="timestamp",
            require_datetime=True,
            require_integer=False,
        )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.landed_at_column_name,
            column_role="landed_at",
            require_datetime=True,
            require_integer=False,
        )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.cursor_column_name,
            column_role="cursor",
            require_datetime=False,
            require_integer=True,
        )
        validate_injected_alias_collisions(
            column_types_by_name=column_types_by_name,
            external_source_replay_config=external_source_replay_config,
        )
