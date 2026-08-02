"""Deterministic text assembly for compile artifacts."""

from streambuild.compiler.testing.models import SqlTestCase


def normalized_sql(sql: str) -> str:
    return sql.rstrip() + "\n"


def static_test_sql(*, test_case: SqlTestCase) -> str:
    return normalized_sql(test_case.query)
