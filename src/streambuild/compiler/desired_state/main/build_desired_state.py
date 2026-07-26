"""Build project-level desired-state graphs from compiled pipelines."""

from __future__ import annotations

from streambuild.compiler.compile.models import (
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ExternalSourceReplayConfig,
    ObjectKey,
)
from streambuild.compiler.desired_state._helpers.objects import (
    external_source_replay_config,
    managed_landing_objects,
    source_anchor_key,
)


def build_desired_state(compiled_pipelines: tuple[CompiledPipeline, ...]) -> DesiredState:
    """Build a flat desired object graph from compiled pipelines."""

    objects: list[DesiredKafkaTable | DesiredTable | DesiredMaterializedView] = []
    replay_anchor_keys: set[ObjectKey] = set()
    mutable_ref_warning_keys: set[ObjectKey] = set()
    external_source_replay_configs: list[ExternalSourceReplayConfig] = []
    for compiled_pipeline in compiled_pipelines:
        objects.extend(managed_landing_objects(compiled_pipeline))
        replay_anchor_keys.add(source_anchor_key(compiled_pipeline))
        resolved_replay_config: ExternalSourceReplayConfig | None = external_source_replay_config(
            compiled_pipeline
        )
        if resolved_replay_config is not None:
            external_source_replay_configs.append(resolved_replay_config)
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
