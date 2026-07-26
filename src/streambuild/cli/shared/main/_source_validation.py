from __future__ import annotations

from streambuild.cli.shared._helpers.source_validation import (
    build_external_source_replay_config,
    load_source_column_types,
    validate_declared_column,
    validate_injected_alias_collisions,
)
from streambuild.cli.shared.exceptions import CliUserError
from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledPipeline,
    ExternalSourceReplayConfig,
)
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


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
            build_external_source_replay_config(source_step)
        )
        column_types_by_name: dict[str, str] = load_source_column_types(
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
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.partition_column_name,
            column_role="partition",
            require_datetime=False,
        )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.offset_column_name,
            column_role="offset",
            require_datetime=False,
        )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.timestamp_column_name,
            column_role="timestamp",
            require_datetime=True,
        )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.landed_at_column_name,
            column_role="landed_at",
            require_datetime=True,
        )
        validate_declared_column(
            column_types_by_name=column_types_by_name,
            table_name=external_source_replay_config.table_name,
            column_name=external_source_replay_config.cursor_column_name,
            column_role="cursor",
            require_datetime=False,
        )
        validate_injected_alias_collisions(
            column_types_by_name=column_types_by_name,
            external_source_replay_config=external_source_replay_config,
        )
