"""Extract typed logical SQL references."""

from streambuild.compiler.sql_analysis._helpers.scanning import extract_references_impl
from streambuild.compiler.sql_analysis.models import SqlReference


def extract_references(sql: str) -> tuple[SqlReference, ...]:
    """Return source-located logical references in authored order."""

    return extract_references_impl(sql)
