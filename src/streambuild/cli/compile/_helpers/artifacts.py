"""Artifact-writing helpers for the compile command."""

from pathlib import Path

from sqlglot import exp, parse_one


def format_clickhouse_sql(sql: str) -> str:
    """Pretty format ClickHouse SQL for emitted artifacts."""

    expression: exp.Expr = parse_one(sql, dialect="clickhouse")
    return expression.sql(dialect="clickhouse", pretty=True)


def write_text(*, path: Path, contents: str) -> None:
    """Write compile artifact text to disk."""

    path.write_text(contents, encoding="utf-8")
