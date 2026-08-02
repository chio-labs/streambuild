"""Preserve managed source and landing resources and block on drift."""

from __future__ import annotations

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.compiler.compile.models import (
    CompiledSource,
    DesiredMaterializedView,
    LogicalResourceKey,
)
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.executor.direct.exceptions import DirectBuildError
from streambuild.executor.population.models import (
    PopulationRealization,
    PopulationSourcePreparation,
)

_KAFKA_BROKER_LIST_SETTING: str = "kafka_broker_list"
_KAFKA_TOPIC_LIST_SETTING: str = "kafka_topic_list"
_KAFKA_FORMAT_SETTING: str = "kafka_format"


def plan_preserved_managed_sources(
    *,
    realized_project: RealizedProject,
    catalog: CatalogSnapshot,
    database: str,
) -> tuple[PopulationSourcePreparation, tuple[PopulationRealization, ...]]:
    """Validate preserved sources and plan absent resources without mutation."""

    resources: tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView, ...] = (
        _managed_source_resources(realized_project=realized_project)
    )
    _reject_managed_source_drift(resources=resources, catalog=catalog)
    preserved_names: list[str] = []
    created_names: list[str] = []
    landing_view_names: list[str] = []
    realizations: list[PopulationRealization] = []
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
    for resource in resources:
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
    return (
        PopulationSourcePreparation(
            preserved_relation_names=tuple(preserved_names),
            created_relation_names=tuple(created_names),
            landing_views=desired_landing_views,
        ),
        tuple(realizations),
    )


def _managed_source_resources(
    *, realized_project: RealizedProject
) -> tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView, ...]:
    resources: list[AdapterManagedSource | AdapterTable | AdapterMaterializedView] = []
    source: CompiledSource
    for source in realized_project.project.sources:
        key: LogicalResourceKey = source.key
        resources.extend(
            resource
            for resource in realized_project.resources_by_logical_key[key]
            if isinstance(resource, (AdapterManagedSource, AdapterTable, AdapterMaterializedView))
        )
    return tuple(resources)


def _reject_managed_source_drift(
    *,
    resources: tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView, ...],
    catalog: CatalogSnapshot,
) -> None:
    drift: list[str] = []
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
    for resource in resources:
        relation: CatalogRelation | None = catalog.relation(resource.name)
        drift.extend(_resource_drift(resource=resource, relation=relation))
    if drift:
        raise DirectBuildError(
            "Direct build preserves managed source infrastructure and cannot continue while it "
            f"has drifted: {'; '.join(drift)}. Recreate the source explicitly before rebuilding."
        )


def _resource_drift(
    *,
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView,
    relation: CatalogRelation | None,
) -> tuple[str, ...]:
    if relation is None:
        return ()
    if isinstance(resource, AdapterManagedSource):
        return _managed_source_drift(resource=resource, relation=relation)
    if isinstance(resource, AdapterTable):
        return _landing_table_drift(resource=resource, relation=relation)
    return _landing_view_drift(resource=resource, relation=relation)


def _managed_source_drift(
    *, resource: AdapterManagedSource, relation: CatalogRelation
) -> tuple[str, ...]:
    actual_settings: dict[str, str] = {
        setting_name: _unquoted(setting_value) for setting_name, setting_value in relation.settings
    }
    expected_settings: dict[str, str] = {
        _KAFKA_BROKER_LIST_SETTING: resource.broker_list,
        _KAFKA_TOPIC_LIST_SETTING: resource.topic,
        _KAFKA_FORMAT_SETTING: resource.format,
        **dict(resource.settings),
    }
    return tuple(
        f"{relation.name} setting '{setting_name}' is "
        f"'{actual_settings.get(setting_name)}' but the project declares '{expected_value}'"
        for setting_name, expected_value in expected_settings.items()
        if actual_settings.get(setting_name) != expected_value
    )


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
