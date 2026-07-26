"""Replace logical ref markers in SQL with resolved relation names."""

from __future__ import annotations

from sqlglot import exp, parse_one

from streambuild.compiler.compile._helpers.refs import (
    _parse_resolved_relation_expression,
    _parse_table_ref,
)
from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.models import ParsedRef


def replace_refs(*, sql: str, resolver: dict[str, str]) -> str:
    """Replace logical refs with resolved SQL relation surfaces."""

    expression: exp.Expr = parse_one(sql, dialect="clickhouse")
    for table in expression.find_all(exp.Table):
        parsed_ref: ParsedRef | None = _parse_table_ref(table)
        if parsed_ref is None:
            continue
        name: str = parsed_ref.name
        if name not in resolver:
            raise PipelineCompileError(f"Unresolved ref: {name}")
        resolved_expression: exp.Expression = _parse_resolved_relation_expression(resolver[name])
        table_alias: exp.TableAlias | None = table.args.get("alias")
        if table_alias is not None and resolved_expression.args.get("alias") is None:
            resolved_expression.set("alias", table_alias.copy())
        table.replace(resolved_expression)

    return expression.sql(dialect="clickhouse")
