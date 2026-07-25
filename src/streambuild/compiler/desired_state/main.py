"""Build project-level desired-state graphs from compiled pipelines."""

from __future__ import annotations

from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledManagedSource,
    CompiledPipeline,
    DesiredState,
    ExternalSourceReplayConfig,
)
from streambuild.compiler.shared.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    ObjectKey,
)


def build_desired_state(compiled_pipelines: tuple[CompiledPipeline, ...]) -> DesiredState:
    """Build a flat desired object graph from compiled pipelines."""

    objects: list[DesiredKafkaTable | DesiredTable | DesiredMaterializedView] = []
    replay_anchor_keys: set[ObjectKey] = set()
    mutable_ref_warning_keys: set[ObjectKey] = set()
    external_source_replay_configs: list[ExternalSourceReplayConfig] = []
    for compiled_pipeline in compiled_pipelines:
        objects.extend(_managed_landing_objects(compiled_pipeline))
        replay_anchor_keys.add(_source_anchor_key(compiled_pipeline))
        external_source_replay_config: ExternalSourceReplayConfig | None = (
            _external_source_replay_config(compiled_pipeline)
        )
        if external_source_replay_config is not None:
            external_source_replay_configs.append(external_source_replay_config)
        for compiled_transform in compiled_pipeline.transforms:
            objects.extend((compiled_transform.target_table, compiled_transform.materialized_view))
            if compiled_transform.replay_anchor_eligible:
                replay_anchor_keys.add(compiled_transform.target_table.key)
            if compiled_transform.has_mutable_refs:
                mutable_ref_warning_keys.add(compiled_transform.target_table.key)

    sorted_objects: tuple[DesiredKafkaTable | DesiredTable | DesiredMaterializedView, ...] = tuple(
        sorted(objects, key=lambda object_: (object_.key.object_type, object_.key.name))
    )
    return DesiredState(
        objects=sorted_objects,
        replay_anchor_keys=frozenset(replay_anchor_keys),
        mutable_ref_warning_keys=frozenset(mutable_ref_warning_keys),
        external_source_replay_configs=tuple(
            sorted(external_source_replay_configs, key=lambda config: config.table_name)
        ),
    )


def _managed_landing_objects(
    compiled_pipeline: CompiledPipeline,
) -> tuple[DesiredKafkaTable | DesiredTable | DesiredMaterializedView, ...]:
    if not isinstance(compiled_pipeline.source, CompiledManagedSource):
        return ()
    managed_source: CompiledManagedSource = compiled_pipeline.source
    return (managed_source.kafka_table, managed_source.raw_table, managed_source.materialized_view)


def _source_anchor_key(compiled_pipeline: CompiledPipeline) -> ObjectKey:
    if isinstance(compiled_pipeline.source, CompiledExternalSource):
        return compiled_pipeline.source.source_key
    return compiled_pipeline.source.raw_table.key


def _external_source_replay_config(
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
