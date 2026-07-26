"""Desired object assembly helpers."""

from __future__ import annotations

from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledManagedSource,
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    ExternalSourceReplayConfig,
    ObjectKey,
)


def managed_landing_objects(
    compiled_pipeline: CompiledPipeline,
) -> tuple[DesiredKafkaTable | DesiredTable | DesiredMaterializedView, ...]:
    if not isinstance(compiled_pipeline.source, CompiledManagedSource):
        return ()
    managed_source: CompiledManagedSource = compiled_pipeline.source
    return (managed_source.kafka_table, managed_source.raw_table, managed_source.materialized_view)


def source_anchor_key(compiled_pipeline: CompiledPipeline) -> ObjectKey:
    if isinstance(compiled_pipeline.source, CompiledExternalSource):
        return compiled_pipeline.source.source_key
    return compiled_pipeline.source.raw_table.key


def external_source_replay_config(
    compiled_pipeline: CompiledPipeline,
) -> ExternalSourceReplayConfig | None:
    if not isinstance(compiled_pipeline.source, CompiledExternalSource):
        return None
    external_source: CompiledExternalSource = compiled_pipeline.source
    return ExternalSourceReplayConfig(
        key=external_source.source_key,
        table_name=external_source.source.table_name,
        source_kind=external_source.source.kind,
        replay_boundary_mode=external_source.source.replay_boundary.mode,
        partition_column_name=external_source.source.replay_boundary.columns.partition,
        offset_column_name=external_source.source.replay_boundary.columns.offset,
        timestamp_column_name=external_source.source.replay_boundary.columns.timestamp,
        landed_at_column_name=external_source.source.replay_boundary.columns.landed_at,
        cursor_column_name=external_source.source.replay_boundary.columns.cursor,
    )
