"""Rewrite staged shadow queries onto deployment-suffixed physical relations."""

from streambuild.adapter.constants import ADAPTER_DATABASE_PLACEHOLDER
from streambuild.compiler.compile.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.sql_analysis.main.rewrite_query import rewrite_query
from streambuild.compiler.sql_analysis.main.rewrite_template_query import rewrite_template_query
from streambuild.compiler.sql_analysis.models import SqlQueryRewriteResult, SqlRelationRewrite


def rewrite_shadow_query(*, query: str, physical_name_by_key: dict[ObjectKey, str]) -> str:
    """Rewrite one canonical query's logical relations onto physical names."""

    result: SqlQueryRewriteResult = rewrite_query(
        sql=query,
        dialect="clickhouse",
        relation_rewrites=_shadow_relation_rewrites(physical_name_by_key),
    )
    return result.query


def rewrite_shadow_template(*, template: str, physical_name_by_key: dict[ObjectKey, str]) -> str:
    """Rewrite one database template's relations while preserving author bytes."""

    result: SqlQueryRewriteResult = rewrite_template_query(
        template=template,
        dialect="clickhouse",
        database_placeholder=ADAPTER_DATABASE_PLACEHOLDER,
        relation_rewrites=_shadow_relation_rewrites(physical_name_by_key),
    )
    return result.query


def _shadow_relation_rewrites(
    physical_name_by_key: dict[ObjectKey, str],
) -> tuple[SqlRelationRewrite, ...]:
    return tuple(
        SqlRelationRewrite(
            source_name=key.name,
            target_relation=physical_name,
            source_databases=(None, ADAPTER_DATABASE_PLACEHOLDER),
            preserve_source_database=True,
        )
        for key, physical_name in physical_name_by_key.items()
        if key.object_type == DESIRED_OBJECT_TYPE_TABLE
    )
