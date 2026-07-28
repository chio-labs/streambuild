from streambuild.compiler.sql_analysis._helpers.polyglot import (
    generate_sql_tree,
    parse_sql_tree,
)


def canonicalize_sql(*, sql: str, dialect: str) -> str:
    """Parse and generate one SQL statement through the mandatory analysis engine."""

    tree: dict[str, object] = parse_sql_tree(sql=sql, dialect=dialect)
    return generate_sql_tree(tree=tree, dialect=dialect)
