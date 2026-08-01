"""Normalize a direct closure into the shared population contract."""

from streambuild.adapter.models import AdapterMaterializedView, AdapterTable, AdapterView
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
    LogicalResourceKey,
    ObjectKey,
)
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.models import DirectPlan, DirectReplayRoot
from streambuild.executor.population.models import PopulationObject, PopulationPlan, PopulationRoot


def build_direct_population_plan(
    *, plan: DirectPlan, realized_project: RealizedProject
) -> PopulationPlan:
    """Map direct logical scope to identity-named physical population."""

    desired_state: DesiredState = realized_project.desired_state
    desired_key_by_name: dict[str, ObjectKey] = {
        object_.name: object_.key
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable | DesiredMaterializedView | DesiredView)
    }
    planned_keys: tuple[ObjectKey, ...] = _resource_keys(
        model_keys=plan.execution_scope,
        realized_project=realized_project,
        desired_key_by_name=desired_key_by_name,
    )
    return PopulationPlan(
        execution_id="direct",
        roots=tuple(
            _population_root(
                root=root,
                realized_project=realized_project,
                desired_state=desired_state,
                desired_key_by_name=desired_key_by_name,
            )
            for root in plan.replay_roots
        ),
        objects=tuple(
            PopulationObject(logical_key=key, physical_name=key.name) for key in planned_keys
        ),
    )


def _population_root(
    *,
    root: DirectReplayRoot,
    realized_project: RealizedProject,
    desired_state: DesiredState,
    desired_key_by_name: dict[str, ObjectKey],
) -> PopulationRoot:
    root_relation_name: str = _table_relation_name(
        key=root.model_key, realized_project=realized_project
    )
    affected_keys: tuple[ObjectKey, ...] = _resource_keys(
        model_keys=root.propagated_model_keys,
        realized_project=realized_project,
        desired_key_by_name=desired_key_by_name,
    )
    return PopulationRoot(
        root_key=desired_key_by_name[root_relation_name],
        affected_keys=affected_keys,
        upstream_boundary_key=_anchor_key(
            relation_name=root.driving_input_relation_name,
            desired_state=desired_state,
            desired_key_by_name=desired_key_by_name,
        ),
        replay_lineage_mode=root.replay_boundary_mode,
    )


def _table_relation_name(*, key: LogicalResourceKey, realized_project: RealizedProject) -> str:
    return next(
        resource.name
        for resource in realized_project.resources_by_logical_key[key]
        if isinstance(resource, AdapterTable)
    )


def _resource_keys(
    *,
    model_keys: tuple[LogicalResourceKey, ...],
    realized_project: RealizedProject,
    desired_key_by_name: dict[str, ObjectKey],
) -> tuple[ObjectKey, ...]:
    keys: list[ObjectKey] = []
    model_key: LogicalResourceKey
    for model_key in model_keys:
        resource: object
        for resource in realized_project.resources_by_logical_key[model_key]:
            if isinstance(resource, AdapterTable | AdapterMaterializedView | AdapterView):
                keys.append(desired_key_by_name[resource.name])
    return tuple(keys)


def _anchor_key(
    *,
    relation_name: str,
    desired_state: DesiredState,
    desired_key_by_name: dict[str, ObjectKey],
) -> ObjectKey:
    direct_key: ObjectKey | None = desired_key_by_name.get(relation_name)
    if direct_key is not None:
        return direct_key
    return next(
        config.key
        for config in desired_state.external_source_replay_configs
        if config.table_name == relation_name
    )
