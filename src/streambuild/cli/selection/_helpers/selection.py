"""Selection resolution helpers for CLI commands."""

from __future__ import annotations

from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.selection.constants import (
    PIPELINE_SELECTOR_NAMESPACE,
    SELECTOR_NAMESPACE_SEPARATOR,
)
from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledManagedSource,
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ObjectKey,
)
from streambuild.compiler.planner.main.build_reverse_deps import build_reverse_deps
from streambuild.compiler.planner.main.topologically_order_keys import topologically_order_keys
from streambuild.spec.types import ReplayLineageMode


def resolve_selected_model_keys(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    selectors: tuple[str, ...],
) -> frozenset[ObjectKey]:
    pipeline_model_keys: dict[str, tuple[ObjectKey, ...]] = model_keys_by_pipeline(
        compiled_pipelines=compiled_pipelines
    )
    model_key_by_name: dict[str, ObjectKey] = {
        transform.transform.name: transform.target_table.key
        for compiled_pipeline in compiled_pipelines
        for transform in compiled_pipeline.transforms
    }
    selected_model_keys: set[ObjectKey] = set()
    selector: str
    for selector in selectors:
        if selector.startswith("+") or selector.endswith("+"):
            raise CliUserError(
                "Unsupported selector syntax '"
                f"{selector}"
                "'. StreamBuild selections already include required downstream closure, "
                "so '+' is not supported."
            )
        if SELECTOR_NAMESPACE_SEPARATOR not in selector:
            model_key: ObjectKey | None = model_key_by_name.get(selector)
            if model_key is None:
                raise CliUserError(f"Unknown selected model '{selector}'")
            selected_model_keys.add(model_key)
            continue

        selector_kind: str
        selector_value: str
        selector_kind, selector_value = selector.split(SELECTOR_NAMESPACE_SEPARATOR, 1)
        if selector_kind != PIPELINE_SELECTOR_NAMESPACE:
            raise CliUserError(f"Unsupported selector namespace '{selector_kind}' in '{selector}'")
        pipeline_keys: tuple[ObjectKey, ...] | None = pipeline_model_keys.get(selector_value)
        if pipeline_keys is None:
            raise CliUserError(f"Unknown selected pipeline '{selector_value}'")
        if not pipeline_keys:
            raise CliUserError(f"Selected pipeline '{selector_value}' does not define any models")
        selected_model_keys.update(pipeline_keys)

    return frozenset(selected_model_keys)


def expand_included_keys(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    desired_state: DesiredState,
    selected_model_keys: frozenset[ObjectKey],
) -> frozenset[ObjectKey]:
    reverse_deps: dict[ObjectKey, tuple[ObjectKey, ...]] = build_reverse_deps(desired_state)
    object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, (DesiredTable, DesiredMaterializedView))
    }
    included_keys: set[ObjectKey] = set(selected_model_keys)
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        pipeline_model_keys: frozenset[ObjectKey] = frozenset(
            transform.target_table.key for transform in compiled_pipeline.transforms
        )
        if not (pipeline_model_keys & selected_model_keys):
            continue
        included_keys.update(pipeline_source_keys(compiled_pipeline))
    stack: list[ObjectKey] = list(selected_model_keys)

    while stack:
        current_key: ObjectKey = stack.pop()
        downstream_key: ObjectKey
        for downstream_key in reverse_deps.get(current_key, ()):
            if downstream_key in included_keys:
                continue
            included_keys.add(downstream_key)
            stack.append(downstream_key)

    changed: bool = True
    while changed:
        changed = False
        key: ObjectKey
        for key in tuple(included_keys):
            desired_object: DesiredTable | DesiredMaterializedView | None = object_by_key.get(key)
            if desired_object is None:
                continue
            dep_key: ObjectKey
            for dep_key in desired_object.deps:
                if dep_key in included_keys:
                    continue
                included_keys.add(dep_key)
                changed = True

    return frozenset(included_keys)


def filter_desired_state(
    *,
    desired_state: DesiredState,
    included_keys: frozenset[ObjectKey],
) -> DesiredState:
    ordered_keys: tuple[ObjectKey, ...] = topologically_order_keys(
        desired_state=desired_state, included_keys=set(included_keys)
    )
    object_by_key: dict[ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView] = {
        object_.key: object_ for object_ in desired_state.objects if object_.key in included_keys
    }
    filtered_objects: tuple[DesiredKafkaTable | DesiredTable | DesiredMaterializedView, ...] = (
        tuple(object_by_key[key] for key in ordered_keys)
    )
    return DesiredState(
        objects=filtered_objects,
        replay_anchor_keys=frozenset(
            key for key in desired_state.replay_anchor_keys if key in included_keys
        ),
        mutable_ref_warning_keys=frozenset(
            key for key in desired_state.mutable_ref_warning_keys if key in included_keys
        ),
        external_source_replay_configs=tuple(
            config
            for config in desired_state.external_source_replay_configs
            if config.key in included_keys
        ),
    )


def pipeline_source_keys(compiled_pipeline: CompiledPipeline) -> frozenset[ObjectKey]:
    if isinstance(compiled_pipeline.source, CompiledExternalSource):
        return frozenset({compiled_pipeline.source.source_key})
    managed_source: CompiledManagedSource = compiled_pipeline.source
    return frozenset(
        {
            managed_source.kafka_table.key,
            managed_source.raw_table.key,
            managed_source.materialized_view.key,
        }
    )


def resolve_replay_lineage_mode(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    selected_model_keys: frozenset[ObjectKey],
) -> ReplayLineageMode:
    replay_lineage_modes: set[ReplayLineageMode] = set()
    selected_pipeline_modes: list[tuple[str, ReplayLineageMode]] = []
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        pipeline_model_keys: frozenset[ObjectKey] = frozenset(
            transform.target_table.key for transform in compiled_pipeline.transforms
        )
        if selected_model_keys and not (pipeline_model_keys & selected_model_keys):
            continue
        replay_lineage_modes.add(compiled_pipeline.effective_replay_lineage_mode)
        selected_pipeline_modes.append(
            (
                compiled_pipeline.pipeline.name,
                compiled_pipeline.effective_replay_lineage_mode,
            )
        )
    if len(replay_lineage_modes) != 1:
        mode_details: str = ", ".join(
            f"{pipeline_name}={replay_lineage_mode}"
            for pipeline_name, replay_lineage_mode in sorted(selected_pipeline_modes)
        )
        raise CliUserError(f"Selected pipelines disagree on replay_lineage_mode: {mode_details}")
    return next(iter(replay_lineage_modes))


def model_keys_by_pipeline(
    *, compiled_pipelines: tuple[CompiledPipeline, ...]
) -> dict[str, tuple[ObjectKey, ...]]:
    keys_by_pipeline: dict[str, tuple[ObjectKey, ...]] = {}
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        keys_by_pipeline[compiled_pipeline.pipeline.name] = tuple(
            transform.target_table.key for transform in compiled_pipeline.transforms
        )
    return keys_by_pipeline
