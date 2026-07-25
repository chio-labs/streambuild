"""Render CREATE MATERIALIZED VIEW DDL from desired-state models."""

from sqlglot import exp, parse_one

from streambuild.compiler.shared.models import DesiredMaterializedView, MaterializedViewSpec


def render_create_materialized_view_ddl(
    materialized_view: DesiredMaterializedView, database: str
) -> str:
    """Render CREATE MATERIALIZED VIEW DDL for a desired materialized view."""

    spec: MaterializedViewSpec = materialized_view.spec
    qualified_query: str = _qualify_table_reference(
        query=spec.query,
        table_name=spec.source_table_name,
        database=database,
    )
    return (
        f"CREATE MATERIALIZED VIEW {database}.{materialized_view.name}\n"
        f"TO {database}.{spec.target_table_name} AS\n"
        f"{qualified_query}"
    )


def _qualify_table_reference(query: str, table_name: str, database: str) -> str:
    """Qualify unqualified table references in rendered materialized-view SQL."""

    expression: exp.Expr = parse_one(query, dialect="clickhouse")
    for table in expression.find_all(exp.Table):
        if table.db:
            continue
        table.set("db", exp.to_identifier(database))
    return expression.sql(dialect="clickhouse", pretty=True)
