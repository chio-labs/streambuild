"""Normalize one SQL data type through the mandatory analysis boundary."""

from streambuild.compiler.sql_analysis._helpers.polyglot import normalize_data_type_sql


def normalize_sql_data_type(*, sql: str, dialect: str) -> str:
    """Return one canonical SQL data type."""

    return normalize_data_type_sql(sql=sql, dialect=dialect)
