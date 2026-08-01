"""Build neutral adapter resources for staged physical objects."""

from dataclasses import replace

from streambuild.adapter.constants import ADAPTER_DATABASE_PLACEHOLDER
from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
    AdapterView,
)
from streambuild.compiler.compile.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredTable,
    DesiredView,
    MaterializedViewSpec,
    ObjectKey,
    ViewSpec,
)
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource
from streambuild.compiler.sql_analysis.main.rewrite_query import rewrite_query
from streambuild.compiler.sql_analysis.models import SqlQueryRewriteResult, SqlRelationRewrite


def build_shadow_adapter_resource(
    *,
    desired_object: DesiredTable | DesiredMaterializedView | DesiredView,
    physical_name: str,
    physical_name_by_key: dict[ObjectKey, str],
) -> (
    AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterView | AdapterStableView
):
    """Build a staged physical resource while rewriting logical references."""

    if isinstance(desired_object, DesiredTable):
        return build_adapter_resource(
            replace(
                desired_object,
                key=replace(desired_object.key, name=physical_name),
            )
        )
    if isinstance(desired_object, DesiredView):
        rewritten_query: str = _rewrite_query(
            query=desired_object.query,
            physical_name_by_key=physical_name_by_key,
        )
        database_template: str = _rewrite_query(
            query=(
                desired_object.query
                if desired_object.spec.database_template is None
                else desired_object.spec.database_template
            ),
            physical_name_by_key=physical_name_by_key,
        )
        return build_adapter_resource(
            replace(
                desired_object,
                key=replace(desired_object.key, name=physical_name),
                spec=ViewSpec(query=rewritten_query, database_template=database_template),
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
                database_template=_rewrite_query(
                    query=(
                        desired_object.query
                        if desired_object.spec.database_template is None
                        else desired_object.spec.database_template
                    ),
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
    result: SqlQueryRewriteResult = rewrite_query(
        sql=query,
        dialect="clickhouse",
        relation_rewrites=tuple(
            SqlRelationRewrite(
                source_name=key.name,
                target_relation=physical_name,
                source_databases=(None, ADAPTER_DATABASE_PLACEHOLDER),
                preserve_source_database=True,
            )
            for key, physical_name in physical_name_by_key.items()
            if key.object_type == DESIRED_OBJECT_TYPE_TABLE
        ),
    )
    return result.query
