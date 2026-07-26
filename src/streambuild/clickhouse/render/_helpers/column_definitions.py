"""Render ClickHouse column definitions shared by table renderers."""

from streambuild.compiler.compile.models import Column


def render_column_definition(column: Column) -> str:
    """Render a single column definition, including its default when present."""

    if column.default is None:
        return f"{column.name} {column.type}"
    return f"{column.name} {column.type} DEFAULT {column.default}"
