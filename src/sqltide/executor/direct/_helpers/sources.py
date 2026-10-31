"""Preserve managed landing resources, recreate drifted Kafka sources, block on other drift."""

from __future__ import annotations

from sqltide.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    CatalogRelation,
    CatalogSnapshot,
)
from sqltide.adapters.clickhouse.main.database_scoped_consumer_group import (
    database_scoped_consumer_group,
)
from sqltide.compiler.compile.models import (
    CompiledPipeline,
    CompiledSource,
    CompiledTableModel,
    DesiredMaterializedView,
    LogicalResourceKey,
)
from sqltide.compiler.discovery.types import PipelineMode
from sqltide.compiler.pipeline.models import RealizedProject
from sqltide.compiler.planner.models import DirectPlan, DirectSourceDriftSelection
from sqltide.executor.direct.exceptions import DirectBuildError
from sqltide.executor.direct.models import DriftedManagedSource
from sqltide.executor.population.models import (
    PopulationManagedSource,
    PopulationRealization,
    PopulationSourcePreparation,
    PopulationSourceRecreation,
)

_KAFKA_BROKER_LIST_SETTING: str = "kafka_broker_list"
_KAFKA_TOPIC_LIST_SETTING: str = "kafka_topic_list"
_KAFKA_FORMAT_SETTING: str = "kafka_format"
_KAFKA_GROUP_NAME_SETTING: str = "kafka_group_name"
_MASKED_SETTING_VALUE: str = "[HIDDEN]"


def plan_preserved_managed_sources(
    *,
    plan: DirectPlan,
    realized_project: RealizedProject,
    catalog: CatalogSnapshot,
    database: str,
) -> tuple[PopulationSourcePreparation, tuple[PopulationRealization, ...]]:
    """Validate preserved sources and plan absent or recreated resources without mutation."""

    reader_pipelines_by_source: dict[LogicalResourceKey, tuple[str, ...]] = _managed_source_keys(
        plan=plan, realized_project=realized_project
    )
    resources: tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView, ...] = (
        _managed_source_resources(
            realized_project=realized_project,
            source_keys=frozenset(reader_pipelines_by_source),
        )
    )
    recreated_sources: tuple[PopulationSourceRecreation, ...] = _plan_source_recreations(
        resources=resources,
        catalog=catalog,
        database=database,
        prerequisite_hints=_unselected_source_hints(
            realized_project=realized_project,
            reader_pipelines_by_source=reader_pipelines_by_source,
        ),
        selection_notes=_source_drift_selection_notes(plan=plan, realized_project=realized_project),
    )
    recreated_names: frozenset[str] = frozenset(
        recreation.managed_source.resource.name for recreation in recreated_sources
    )
    preserved_names: list[str] = []
    created_names: list[str] = []
    landing_view_names: list[str] = []
    realizations: list[PopulationRealization] = []
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
    for resource in resources:
        if resource.name in recreated_names:
            continue
        if resource.name in catalog.relation_names():
            preserved_names.append(resource.name)
        else:
            created_names.append(resource.name)
            if isinstance(resource, AdapterMaterializedView):
                landing_view_names.append(resource.name)
            else:
                realizations.append(PopulationRealization(resource=resource, database=database))
    desired_landing_views: tuple[DesiredMaterializedView, ...] = tuple(
        desired
        for desired in realized_project.desired_state.objects
        if isinstance(desired, DesiredMaterializedView) and desired.name in landing_view_names
    )
    managed_sources: tuple[PopulationManagedSource, ...] = tuple(
        PopulationManagedSource(resource=resource, database=database)
        for resource in resources
        if isinstance(resource, AdapterManagedSource)
    )
    return (
        PopulationSourcePreparation(
            preserved_relation_names=tuple(preserved_names),
            created_relation_names=tuple(created_names),
            landing_views=desired_landing_views,
            managed_sources=managed_sources,
            recreated_sources=recreated_sources,
        ),
        tuple(realizations),
    )


def _managed_source_keys(
    *, plan: DirectPlan, realized_project: RealizedProject
) -> dict[LogicalResourceKey, tuple[str, ...]]:
    """Map each relevant source to the owning pipelines a build must select to recreate it."""

    execution_model_keys: frozenset[LogicalResourceKey] = frozenset(plan.execution_scope)
    relevant_model_keys: frozenset[LogicalResourceKey] = frozenset(
        (*plan.execution_scope, *(item.key for item in plan.prerequisite_scope))
    )
    source_keys: set[LogicalResourceKey] = set()
    executed_pipeline_names: set[str] = set()
    pipeline: CompiledPipeline
    for pipeline in realized_project.project.pipelines:
        if pipeline.source is None:
            continue
        if any(model.key in relevant_model_keys for model in pipeline.models):
            source_keys.add(pipeline.source.key)
        if any(model.key in execution_model_keys for model in pipeline.models):
            executed_pipeline_names.add(pipeline.pipeline.name)
    owners_by_source: dict[LogicalResourceKey, tuple[str, ...]] = _source_owner_pipelines(
        realized_project=realized_project
    )
    return {
        key: ()
        if executed_pipeline_names.intersection(owners_by_source[key])
        else owners_by_source[key]
        for key in source_keys
    }


def _source_owner_pipelines(
    *, realized_project: RealizedProject
) -> dict[LogicalResourceKey, tuple[str, ...]]:
    """Map each source to its direct readers, or to every declaring pipeline when none read it."""

    source_pipelines: dict[LogicalResourceKey, list[str]] = {}
    reader_pipelines: dict[LogicalResourceKey, list[str]] = {}
    pipeline: CompiledPipeline
    for pipeline in realized_project.project.pipelines:
        if pipeline.source is None:
            continue
        source_pipelines.setdefault(pipeline.source.key, []).append(pipeline.pipeline.name)
        if any(
            isinstance(model, CompiledTableModel)
            and model.transform.source == pipeline.source.key.name
            for model in pipeline.models
        ):
            reader_pipelines.setdefault(pipeline.source.key, []).append(pipeline.pipeline.name)
    return {
        key: tuple(reader_pipelines.get(key, pipeline_names))
        for key, pipeline_names in source_pipelines.items()
    }


def drifted_managed_sources(
    *, realized_project: RealizedProject, catalog: CatalogSnapshot
) -> tuple[DriftedManagedSource, ...]:
    """Return each deployed managed source whose settings drifted, with its sorted owners."""

    owners_by_source: dict[LogicalResourceKey, tuple[str, ...]] = _source_owner_pipelines(
        realized_project=realized_project
    )
    drifted: list[DriftedManagedSource] = []
    key: LogicalResourceKey
    for key in sorted(owners_by_source, key=lambda source_key: source_key.name):
        drifted_setting_names: list[str] = []
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
        for resource in _managed_source_resources(
            realized_project=realized_project, source_keys=frozenset((key,))
        ):
            relation: CatalogRelation | None = catalog.relation(resource.name)
            if isinstance(resource, AdapterManagedSource) and relation is not None:
                drifted_setting_names.extend(
                    _managed_source_drift(resource=resource, relation=relation)
                )
        if drifted_setting_names:
            drifted.append(
                DriftedManagedSource(
                    source_key=key,
                    owner_pipeline_names=tuple(sorted(owners_by_source[key])),
                    drifted_setting_names=tuple(drifted_setting_names),
                )
            )
    return tuple(drifted)


def _unselected_source_hints(
    *,
    realized_project: RealizedProject,
    reader_pipelines_by_source: dict[LogicalResourceKey, tuple[str, ...]],
) -> dict[str, str]:
    """Explain, per Kafka relation, how to select a build that may recreate the source."""

    direct_pipeline_names: frozenset[str] = frozenset(
        pipeline.pipeline.name
        for pipeline in realized_project.project.pipelines
        if PipelineMode(pipeline.pipeline.mode) == PipelineMode.DIRECT
    )
    hints: dict[str, str] = {}
    key: LogicalResourceKey
    pipeline_names: tuple[str, ...]
    for key, pipeline_names in reader_pipelines_by_source.items():
        if not pipeline_names:
            continue
        readers: str = ", ".join(repr(name) for name in sorted(pipeline_names))
        direct_readers: tuple[str, ...] = tuple(
            sorted(name for name in pipeline_names if name in direct_pipeline_names)
        )
        selectors: str = ", ".join(
            f"pipeline:{name}" for name in (direct_readers[:1] or sorted(pipeline_names))
        )
        hint: str = (
            f"source '{key.name}' is read directly only by pipeline {readers}, which this "
            f"build does not rebuild; include {selectors} in the selection to recreate it "
            "with the declared settings"
        )
        hints.update(
            (resource.name, hint)
            for resource in realized_project.resources_by_logical_key[key]
            if isinstance(resource, AdapterManagedSource)
        )
    return hints


def _source_drift_selection_notes(
    *, plan: DirectPlan, realized_project: RealizedProject
) -> dict[str, str]:
    """Explain, per source relation, why a changed selection rebuilds the owning pipeline."""

    notes: dict[str, str] = {}
    selection: DirectSourceDriftSelection
    for selection in plan.source_drift_selections:
        note: str = (
            f"pipeline '{selection.pipeline_name}' was selected because source "
            f"'{selection.source_key.name}' settings drifted from the project, and "
        )
        notes.update(
            (resource.name, note)
            for resource in realized_project.resources_by_logical_key[selection.source_key]
        )
    return notes


def _managed_source_resources(
    *, realized_project: RealizedProject, source_keys: frozenset[LogicalResourceKey]
) -> tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView, ...]:
    resources: list[AdapterManagedSource | AdapterTable | AdapterMaterializedView] = []
    source: CompiledSource
    for source in realized_project.project.sources:
        key: LogicalResourceKey = source.key
        if key not in source_keys:
            continue
        resources.extend(
            resource
            for resource in realized_project.resources_by_logical_key[key]
            if isinstance(resource, (AdapterManagedSource, AdapterTable, AdapterMaterializedView))
        )
    return tuple(resources)


def _plan_source_recreations(
    *,
    resources: tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView, ...],
    catalog: CatalogSnapshot,
    database: str,
    prerequisite_hints: dict[str, str],
    selection_notes: dict[str, str],
) -> tuple[PopulationSourceRecreation, ...]:
    blocking_drift: list[str] = []
    prerequisite_drift: list[str] = []
    recreations: list[PopulationSourceRecreation] = []
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
    for resource in resources:
        relation: CatalogRelation | None = catalog.relation(resource.name)
        if relation is None:
            continue
        if isinstance(resource, AdapterManagedSource):
            drifted_setting_names: tuple[str, ...] = _managed_source_drift(
                resource=resource, relation=relation
            )
            if not drifted_setting_names:
                continue
            if resource.name in prerequisite_hints:
                prerequisite_drift.append(
                    f"{relation.name} settings ({', '.join(drifted_setting_names)}) differ from "
                    f"the project declaration, but {prerequisite_hints[resource.name]}"
                )
                continue
            consumer_group: str = database_scoped_consumer_group(
                consumer_group=resource.consumer_group,
                database=database,
            )
            blocking_drift.extend(
                f"{selection_notes.get(resource.name, '')}{drift}"
                for drift in _consumer_group_drift(relation=relation, consumer_group=consumer_group)
            )
            landing_view: AdapterMaterializedView = _landing_view(
                managed_source=resource, resources=resources
            )
            recreations.append(
                PopulationSourceRecreation(
                    managed_source=PopulationManagedSource(resource=resource, database=database),
                    landing_view_name=landing_view.name,
                    landing_relation_name=landing_view.target_relation_name,
                    consumer_group=consumer_group,
                    drifted_setting_names=drifted_setting_names,
                )
            )
        elif isinstance(resource, AdapterTable):
            blocking_drift.extend(
                f"{selection_notes.get(resource.name, '')}{drift}"
                for drift in _landing_table_drift(resource=resource, relation=relation)
            )
        else:
            blocking_drift.extend(
                f"{selection_notes.get(resource.name, '')}{drift}"
                for drift in _landing_view_drift(resource=resource, relation=relation)
            )
    if blocking_drift:
        raise DirectBuildError(
            "Direct build preserves managed source infrastructure and cannot continue while it "
            f"has drifted: {'; '.join((*blocking_drift, *prerequisite_drift))}. Recreate the "
            "source explicitly before rebuilding."
        )
    if prerequisite_drift:
        raise DirectBuildError(
            "Direct build preserves managed source infrastructure and cannot continue while it "
            f"has drifted: {'; '.join(prerequisite_drift)}."
        )
    return tuple(recreations)


def _managed_source_drift(
    *, resource: AdapterManagedSource, relation: CatalogRelation
) -> tuple[str, ...]:
    actual_settings: dict[str, str] = _actual_settings(relation=relation)
    expected_settings: dict[str, str] = {
        _KAFKA_BROKER_LIST_SETTING: resource.broker_list,
        _KAFKA_TOPIC_LIST_SETTING: resource.topic,
        _KAFKA_FORMAT_SETTING: resource.format,
        **dict(resource.settings),
    }
    return tuple(
        setting_name
        for setting_name, expected_value in expected_settings.items()
        if actual_settings.get(setting_name) not in {expected_value, _MASKED_SETTING_VALUE}
    )


def _consumer_group_drift(*, relation: CatalogRelation, consumer_group: str) -> tuple[str, ...]:
    actual_group: str | None = _actual_settings(relation=relation).get(_KAFKA_GROUP_NAME_SETTING)
    if actual_group == consumer_group:
        return ()
    return (
        f"{relation.name} consumes as consumer group '{actual_group}' but the project declares "
        f"'{consumer_group}', so recreating it for its changed settings would not resume from "
        "the committed offsets",
    )


def _landing_view(
    *,
    managed_source: AdapterManagedSource,
    resources: tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView, ...],
) -> AdapterMaterializedView:
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
    for resource in resources:
        if (
            isinstance(resource, AdapterMaterializedView)
            and resource.source_relation_name == managed_source.name
        ):
            return resource
    raise DirectBuildError(f"Managed source '{managed_source.name}' has no landing view")


def _actual_settings(*, relation: CatalogRelation) -> dict[str, str]:
    return {
        setting_name: _unquoted(setting_value) for setting_name, setting_value in relation.settings
    }


def _landing_table_drift(*, resource: AdapterTable, relation: CatalogRelation) -> tuple[str, ...]:
    expected_columns: tuple[tuple[str, str], ...] = tuple(
        (column.name, column.type) for column in resource.columns
    )
    actual_columns: tuple[tuple[str, str], ...] = tuple(
        (column.name, column.type) for column in relation.columns
    )
    if expected_columns == actual_columns:
        return ()
    return (f"{relation.name} landing columns no longer match the project declaration",)


def _landing_view_drift(
    *, resource: AdapterMaterializedView, relation: CatalogRelation
) -> tuple[str, ...]:
    if relation.target_relation_name == resource.target_relation_name:
        return ()
    return (
        f"{relation.name} writes to '{relation.target_relation_name}' but the project declares "
        f"'{resource.target_relation_name}'",
    )


def _unquoted(value: str) -> str:
    return value.strip().strip("'")
