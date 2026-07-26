"""Build neutral adapter resources for staged physical objects."""

from dataclasses import replace

from sqlglot import exp, parse_one

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
)
from streambuild.compiler.compile.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredTable,
    MaterializedViewSpec,
    ObjectKey,
)
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource


def build_shadow_adapter_resource(
    *,
    desired_object: DesiredTable | DesiredMaterializedView,
    physical_name: str,
    physical_name_by_key: dict[ObjectKey, str],
) -> AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView:
    """Build a staged physical resource while rewriting logical references."""

    if isinstance(desired_object, DesiredTable):
        return build_adapter_resource(
            replace(
                desired_object,
                key=replace(desired_object.key, name=physical_name),
            )
        )
    source_name: str = _physical_table_name(
        logical_name=desired_object.source_table_name,
        physical_name_by_key=physical_name_by_key,
    )
    target_name: str = _physical_table_name(
        logical_name=desired_object.target_table_name,
        physical_name_by_key=physical_name_by_key,
    )
    return build_adapter_resource(
        replace(
            desired_object,
            key=replace(desired_object.key, name=physical_name),
            spec=MaterializedViewSpec(
                source_table_name=source_name,
                target_table_name=target_name,
                query=_rewrite_query(
                    query=desired_object.query,
                    physical_name_by_key=physical_name_by_key,
                ),
            ),
        )
    )


def _physical_table_name(*, logical_name: str, physical_name_by_key: dict[ObjectKey, str]) -> str:
    key: ObjectKey
    physical_name: str
    for key, physical_name in physical_name_by_key.items():
        if key.object_type == DESIRED_OBJECT_TYPE_TABLE and key.name == logical_name:
            return physical_name
    return logical_name


def _rewrite_query(*, query: str, physical_name_by_key: dict[ObjectKey, str]) -> str:
    expression: exp.Expr = parse_one(query, dialect="clickhouse")
    table_name_to_physical_name: dict[str, str] = {
        key.name: physical_name
        for key, physical_name in physical_name_by_key.items()
        if key.object_type == DESIRED_OBJECT_TYPE_TABLE
    }
    table: exp.Table
    for table in expression.find_all(exp.Table):
        if table.db:
            continue
        physical_name: str | None = table_name_to_physical_name.get(table.name)
        if physical_name is not None:
            table.set("this", exp.to_identifier(physical_name))
    return expression.sql(dialect="clickhouse")
