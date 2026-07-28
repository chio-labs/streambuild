"""Dependency-safe teardown and creation of directly named standard relations."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
)
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.models import StandardPlan, StandardRelationOperation
from streambuild.executor.standard.constants import MODEL_TABLE_RELATION_INDEX
from streambuild.executor.standard.exceptions import StandardBuildError


def drop_planned_relations(
    *, client: AdapterConnection, plan: StandardPlan, database: str
) -> tuple[str, ...]:
    """Drop every planned relation in the plan's reverse dependency order."""

    dropped: list[str] = []
    operation: StandardRelationOperation
    for operation in plan.teardown_operations:
        client.command(f"DROP TABLE IF EXISTS {database}.{operation.relation_name} SYNC")
        dropped.append(operation.relation_name)
    return tuple(dropped)


def create_planned_tables(
    *,
    client: AdapterConnection,
    plan: StandardPlan,
    realized_project: RealizedProject,
    database: str,
) -> tuple[str, ...]:
    """Create every planned target table before dependency-ordered view attachment."""

    resource_by_name: dict[str, AdapterTable | AdapterMaterializedView] = (
        _model_resource_by_relation_name(plan=plan, realized_project=realized_project)
    )
    created: list[str] = []
    operation: StandardRelationOperation
    for operation in plan.creation_operations:
        resource: AdapterTable | AdapterMaterializedView = resource_by_name[operation.relation_name]
        if isinstance(resource, AdapterTable):
            client.realize_resource(resource=resource, database=database, if_not_exists=False)
            created.append(operation.relation_name)
    return tuple(created)


def create_planned_materialized_view(
    *,
    client: AdapterConnection,
    model_key: LogicalResourceKey,
    realized_project: RealizedProject,
    database: str,
) -> str:
    """Attach one canonical model view after its executed dependencies are populated."""

    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
    for resource in realized_project.resources_by_logical_key[model_key]:
        if isinstance(resource, AdapterMaterializedView):
            client.realize_resource(resource=resource, database=database, if_not_exists=False)
            return resource.name
    raise StandardBuildError(
        f"Standard build cannot find the materialized view of model '{model_key.name}'"
    )


def _model_resource_by_relation_name(
    *, plan: StandardPlan, realized_project: RealizedProject
) -> dict[str, AdapterTable | AdapterMaterializedView]:
    resource_by_name: dict[str, AdapterTable | AdapterMaterializedView] = {}
    model_key: LogicalResourceKey
    for model_key in plan.execution_scope:
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView
        for resource in realized_project.resources_by_logical_key[model_key]:
            resource_by_name[resource.name] = _model_resource(
                resource=resource, model_name=model_key.name
            )
    return resource_by_name


def _model_resource(
    *,
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView,
    model_name: str,
) -> AdapterTable | AdapterMaterializedView:
    if isinstance(resource, AdapterManagedSource):
        raise StandardBuildError(
            f"Standard build cannot realize a managed source for model '{model_name}'"
        )
    return resource


def target_relation_name_by_model_name(*, plan: StandardPlan) -> dict[str, str]:
    """Map every executed model to the directly named table replay writes into."""

    return {
        entry.model_key.name: entry.relation_names[MODEL_TABLE_RELATION_INDEX]
        for entry in plan.entries
    }
