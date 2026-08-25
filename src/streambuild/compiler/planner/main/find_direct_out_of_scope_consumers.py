"""Detect actual materialized-view consumers outside a direct execution scope."""

from __future__ import annotations

from streambuild.adapter.models import AdapterMaterializedView, CatalogSnapshot
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.constants import CATALOG_MATERIALIZED_VIEW_ENGINE


def find_direct_out_of_scope_consumers(
    *,
    realized_project: RealizedProject,
    catalog: CatalogSnapshot,
    prerequisite_execution_scope: tuple[LogicalResourceKey, ...],
    execution_scope: tuple[LogicalResourceKey, ...],
) -> tuple[str, ...]:
    """Return actual consumers that prerequisite replay could mutate unexpectedly."""

    rebuilt_relation_names: frozenset[str] = frozenset(
        realized_project.relation_name_by_logical_key[key] for key in prerequisite_execution_scope
    )
    if not rebuilt_relation_names:
        return ()
    in_scope_view_names: set[str] = set()
    for key in execution_scope:
        for resource in realized_project.resources_by_logical_key.get(key, ()):
            if isinstance(resource, AdapterMaterializedView):
                in_scope_view_names.add(resource.name)
    in_scope_materialized_views: frozenset[str] = frozenset(in_scope_view_names)
    return tuple(
        sorted(
            relation.name
            for relation in catalog.relations
            if relation.engine == CATALOG_MATERIALIZED_VIEW_ENGINE
            and relation.name not in in_scope_materialized_views
            and rebuilt_relation_names.intersection(relation.source_relation_names)
        )
    )
