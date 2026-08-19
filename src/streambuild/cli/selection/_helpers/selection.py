"""Selection resolution helpers for CLI commands."""

from __future__ import annotations

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    AdapterView,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.selection.constants import (
    MODEL_SELECTOR_NAMESPACE,
    PIPELINE_SELECTOR_NAMESPACE,
    SELECTOR_NAMESPACE_SEPARATOR,
    UPSTREAM_SELECTOR_PREFIX,
)
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
    LogicalResourceKey,
    ObjectKey,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.graph.main.build_reverse_deps import build_reverse_deps
from streambuild.compiler.graph.main.topologically_order_keys import topologically_order_keys
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.pipeline.types import AdapterResource


def resolve_selected_logical_model_keys(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    selectors: tuple[str, ...],
) -> frozenset[LogicalResourceKey]:
    pipeline_model_keys: dict[str, tuple[LogicalResourceKey, ...]] = model_keys_by_pipeline(
        compiled_pipelines=compiled_pipelines
    )
    model_key_by_name: dict[str, LogicalResourceKey] = {}
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        model: CompiledModel
        for model in compiled_pipeline.models:
            model_key_by_name[model.key.name] = model.key
    selected_model_keys: set[LogicalResourceKey] = set()
    raw_selector: str
    for raw_selector in selectors:
        token: str
        for token in raw_selector.split():
            selected_model_keys.update(
                _resolve_selector_token(
                    token=token,
                    pipeline_model_keys=pipeline_model_keys,
                    model_key_by_name=model_key_by_name,
                )
            )
    return frozenset(selected_model_keys)


def _resolve_selector_token(
    *,
    token: str,
    pipeline_model_keys: dict[str, tuple[LogicalResourceKey, ...]],
    model_key_by_name: dict[str, LogicalResourceKey],
) -> frozenset[LogicalResourceKey]:
    if token.startswith(UPSTREAM_SELECTOR_PREFIX) or token.endswith(UPSTREAM_SELECTOR_PREFIX):
        raise CliUserError(
            "Unsupported selector syntax '"
            f"{token}"
            "'. StreamBuild selections already include required downstream closure, "
            "so '+' is not supported."
        )
    if SELECTOR_NAMESPACE_SEPARATOR not in token:
        return _resolve_bare_selector(
            token=token,
            pipeline_model_keys=pipeline_model_keys,
            model_key_by_name=model_key_by_name,
        )
    namespace: str
    value: str
    namespace, value = token.split(SELECTOR_NAMESPACE_SEPARATOR, 1)
    if namespace == PIPELINE_SELECTOR_NAMESPACE:
        return _resolve_pipeline_selector(value=value, pipeline_model_keys=pipeline_model_keys)
    if namespace == MODEL_SELECTOR_NAMESPACE:
        return _resolve_model_selector(value=value, model_key_by_name=model_key_by_name)
    raise CliUserError(f"Unsupported selector namespace '{namespace}' in '{token}'")


def _resolve_bare_selector(
    *,
    token: str,
    pipeline_model_keys: dict[str, tuple[LogicalResourceKey, ...]],
    model_key_by_name: dict[str, LogicalResourceKey],
) -> frozenset[LogicalResourceKey]:
    if token in pipeline_model_keys:
        return _resolve_pipeline_selector(value=token, pipeline_model_keys=pipeline_model_keys)
    if token in model_key_by_name:
        return frozenset({model_key_by_name[token]})
    raise CliUserError(f"Unknown selected model or pipeline '{token}'")


def _resolve_pipeline_selector(
    *, value: str, pipeline_model_keys: dict[str, tuple[LogicalResourceKey, ...]]
) -> frozenset[LogicalResourceKey]:
    pipeline_keys: tuple[LogicalResourceKey, ...] | None = pipeline_model_keys.get(value)
    if pipeline_keys is None:
        raise CliUserError(f"Unknown selected pipeline '{value}'")
    if not pipeline_keys:
        raise CliUserError(f"Selected pipeline '{value}' does not define any models")
    return frozenset(pipeline_keys)


def _resolve_model_selector(
    *, value: str, model_key_by_name: dict[str, LogicalResourceKey]
) -> frozenset[LogicalResourceKey]:
    model_key: LogicalResourceKey | None = model_key_by_name.get(value)
    if model_key is None:
        raise CliUserError(f"Unknown selected model '{value}'")
    return frozenset({model_key})


def expand_included_keys(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    realized_project: RealizedProject,
    desired_state: DesiredState,
    selected_model_keys: frozenset[ObjectKey],
) -> frozenset[ObjectKey]:
    reverse_deps: dict[ObjectKey, tuple[ObjectKey, ...]] = build_reverse_deps(desired_state)
    object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, (DesiredTable, DesiredMaterializedView, DesiredView))
    }
    included_keys: set[ObjectKey] = set(selected_model_keys)
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        pipeline_model_keys: frozenset[ObjectKey] = physical_model_keys(
            realized_project=realized_project,
            logical_model_keys=frozenset(model.key for model in compiled_pipeline.models),
        )
        if not (pipeline_model_keys & selected_model_keys):
            continue
        included_keys.update(
            pipeline_source_keys(
                compiled_pipeline=compiled_pipeline,
                realized_project=realized_project,
            )
        )
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
            desired_object: DesiredTable | DesiredMaterializedView | DesiredView | None = (
                object_by_key.get(key)
            )
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
    object_by_key: dict[
        ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    ] = {object_.key: object_ for object_ in desired_state.objects if object_.key in included_keys}
    filtered_objects: tuple[
        DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView, ...
    ] = tuple(object_by_key[key] for key in ordered_keys)
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


def pipeline_source_keys(
    *, compiled_pipeline: CompiledPipeline, realized_project: RealizedProject
) -> frozenset[ObjectKey]:
    if compiled_pipeline.source is None:
        return frozenset()
    resources: tuple[AdapterResource, ...] = realized_project.resources_by_logical_key[
        compiled_pipeline.source.key
    ]
    keys: set[ObjectKey] = {_resource_key(resource) for resource in resources}
    keys.add(
        ObjectKey(
            database=None,
            object_type="table",
            name=realized_project.relation_name_by_logical_key[compiled_pipeline.source.key],
        )
    )
    return frozenset(keys)


def resolve_replay_lineage_mode(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    selected_model_keys: frozenset[LogicalResourceKey],
) -> ReplayLineageMode | None:
    replay_lineage_modes: set[ReplayLineageMode] = set()
    selected_pipeline_modes: list[tuple[str, ReplayLineageMode]] = []
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        pipeline_model_keys: frozenset[LogicalResourceKey] = frozenset(
            model.key for model in compiled_pipeline.models
        )
        if selected_model_keys and not (pipeline_model_keys & selected_model_keys):
            continue
        replay_lineage_mode: ReplayLineageMode | None = (
            compiled_pipeline.effective_replay_lineage_mode
        )
        if replay_lineage_mode is None:
            continue
        replay_lineage_modes.add(replay_lineage_mode)
        selected_pipeline_modes.append(
            (
                compiled_pipeline.pipeline.name,
                replay_lineage_mode,
            )
        )
    if len(replay_lineage_modes) > 1:
        mode_details: str = ", ".join(
            f"{pipeline_name}={replay_lineage_mode}"
            for pipeline_name, replay_lineage_mode in sorted(selected_pipeline_modes)
        )
        raise CliUserError(f"Selected pipelines disagree on replay_lineage_mode: {mode_details}")
    return next(iter(replay_lineage_modes), None)


def model_keys_by_pipeline(
    *, compiled_pipelines: tuple[CompiledPipeline, ...]
) -> dict[str, tuple[LogicalResourceKey, ...]]:
    keys_by_pipeline: dict[str, tuple[LogicalResourceKey, ...]] = {}
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        keys_by_pipeline[compiled_pipeline.pipeline.name] = tuple(
            model.key for model in compiled_pipeline.models
        )
    return keys_by_pipeline


def physical_model_keys(
    *,
    realized_project: RealizedProject,
    logical_model_keys: frozenset[LogicalResourceKey],
) -> frozenset[ObjectKey]:
    keys: set[ObjectKey] = set()
    logical_key: LogicalResourceKey
    for logical_key in logical_model_keys:
        if logical_key.resource_type != LogicalResourceType.MODEL:
            raise CliUserError(f"Cannot select non-model logical resource '{logical_key.name}'")
        resource: AdapterTable | AdapterView = next(
            resource
            for resource in realized_project.resources_by_logical_key[logical_key]
            if isinstance(resource, (AdapterTable, AdapterView))
        )
        keys.add(_resource_key(resource))
    return frozenset(keys)


def _resource_key(
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterView,
) -> ObjectKey:
    object_type: str
    if isinstance(resource, AdapterManagedSource):
        object_type = "kafka_table"
    elif isinstance(resource, AdapterMaterializedView):
        object_type = "materialized_view"
    elif isinstance(resource, AdapterView):
        object_type = "view"
    else:
        object_type = "table"
    return ObjectKey(database=None, object_type=object_type, name=resource.name)
