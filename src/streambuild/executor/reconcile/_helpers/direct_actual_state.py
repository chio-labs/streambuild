"""Build direct-mode actual state from plain catalog relations."""

from streambuild.adapter.models import CatalogRelation, CatalogSnapshot
from streambuild.compiler.compile.constants import RAW_TABLE_NAME_PREFIX
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    MaterializedViewSpec,
    TableSpec,
)
from streambuild.compiler.planner.classes.catalog_table_specs import CatalogTableSpecs
from streambuild.compiler.planner.models import (
    ActualMaterializedView,
    ActualState,
    ActualTable,
)


def build_direct_reconcile_actual_state(
    *, desired_state: DesiredState, catalog: CatalogSnapshot, database: str
) -> ActualState:
    """Inspect direct tables and transform views without virtual deployment bindings."""

    table_names: tuple[str, ...] = tuple(
        object_.name
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
        and not object_.name.startswith(RAW_TABLE_NAME_PREFIX)
        and catalog.relation(object_.name) is not None
    )
    table_specs: dict[str, TableSpec] = CatalogTableSpecs.build(
        catalog=catalog,
        database=database,
        table_names=table_names,
    )
    objects: list[ActualTable | ActualMaterializedView] = []
    for desired_object in desired_state.objects:
        if isinstance(desired_object, DesiredTable) and desired_object.name in table_specs:
            objects.append(
                ActualTable(key=desired_object.key, spec=table_specs[desired_object.name])
            )
        elif isinstance(desired_object, DesiredMaterializedView):
            relation: CatalogRelation | None = catalog.relation(desired_object.name)
            if relation is not None:
                objects.append(
                    ActualMaterializedView(
                        key=desired_object.key,
                        spec=MaterializedViewSpec(
                            source_table_name=relation.source_relation_name or "",
                            target_table_name=relation.target_relation_name or "",
                            query=relation.query_sql or "",
                        ),
                    )
                )
    return ActualState(objects=tuple(objects))
