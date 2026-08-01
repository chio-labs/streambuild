"""Preserve managed source and landing resources and block on drift."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.compiler.compile.models import CompiledSource, LogicalResourceKey
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.executor.direct.exceptions import DirectBuildError
from streambuild.executor.population.main._prepare_population_sources import (
    prepare_population_sources,
)
from streambuild.executor.population.models import PopulationSourcePreparation

_KAFKA_BROKER_LIST_SETTING: str = "kafka_broker_list"
_KAFKA_TOPIC_LIST_SETTING: str = "kafka_topic_list"
_KAFKA_FORMAT_SETTING: str = "kafka_format"


def prepare_preserved_managed_sources(
    *,
    client: AdapterConnection,
    realized_project: RealizedProject,
    catalog: CatalogSnapshot,
    database: str,
) -> PopulationSourcePreparation:
    """Validate preserved sources and create only absent passive resources."""

    resources: tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView, ...] = (
        _managed_source_resources(realized_project=realized_project)
    )
    _reject_managed_source_drift(resources=resources, catalog=catalog)
    return prepare_population_sources(
        client=client,
        desired_state=realized_project.desired_state,
        default_database=database,
        existing_relation_names=catalog.relation_names(),
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
