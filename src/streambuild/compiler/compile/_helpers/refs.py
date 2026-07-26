"""Compile-local managed SQL reference helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import cast

from sqlglot import exp, parse_one

from streambuild.compiler.compile.constants import (
    REF_FUNCTION_NAMES,
    REF_TYPE_KEYWORD,
    SOURCE_REF_FUNCTION_NAME,
)
from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.models import ParsedRef
from streambuild.spec.types import RefType, SqlRelationType


def _parse_resolved_relation_expression(resolved_sql: str) -> exp.Expression:
    if any(character.isspace() for character in resolved_sql) or resolved_sql.startswith("("):
        return cast(exp.Expression, parse_one(resolved_sql, dialect="clickhouse"))
    return exp.to_table(resolved_sql)


@lru_cache(maxsize=256)
def _extract_refs_tuple(sql: str) -> tuple[ParsedRef, ...]:
    expression: exp.Expr = parse_one(sql, dialect="clickhouse")
    return tuple(
        parsed_ref
        for table in expression.find_all(exp.Table)
        if (parsed_ref := _parse_table_ref(table)) is not None
    )


def _parse_table_ref(table: exp.Table) -> ParsedRef | None:
    table_expression: exp.Expression = table.this
    if (
        not isinstance(table_expression, exp.Anonymous)
        or table_expression.name not in REF_FUNCTION_NAMES
    ):
        return None
    expressions: list[exp.Expression] = list(table_expression.expressions)
    if len(expressions) not in {1, 2}:
        raise PipelineCompileError(
            "__source(...) and __ref(...) must contain one name argument and optional ref_type"
        )

    ref_name: str = _parse_ref_name(expressions[0])
    ref_type: RefType | None = None
    relation_type: SqlRelationType
    if table_expression.name == SOURCE_REF_FUNCTION_NAME:
        relation_type = SqlRelationType.SOURCE
    else:
        relation_type = SqlRelationType.REF
    if len(expressions) == 2:
        if relation_type != SqlRelationType.REF:
            raise PipelineCompileError("__source(...) must not declare ref_type")
        ref_type = _parse_ref_type(expressions[1])

    return ParsedRef(name=ref_name, relation_type=relation_type, ref_type=ref_type)


def _parse_ref_name(ref_expression: exp.Expression) -> str:
    if isinstance(ref_expression, exp.Literal) and ref_expression.is_string:
        return ref_expression.this
    if isinstance(ref_expression, exp.Column):
        identifier: exp.Expression = ref_expression.this
        if isinstance(identifier, exp.Identifier):
            return identifier.this

    raise PipelineCompileError(
        "__source(...) and __ref(...) name arguments must be a quoted string or identifier"
    )


def _parse_ref_type(ref_type_expression: exp.Expression) -> RefType:
    if not isinstance(ref_type_expression, exp.EQ):
        raise PipelineCompileError(
            "__ref(...) optional second argument must be ref_type='reference' or ref_type='mutable'"
        )

    key_expression: exp.Expression = ref_type_expression.this
    if not isinstance(key_expression, exp.Column):
        raise PipelineCompileError(
            "__ref(...) optional second argument must use the ref_type keyword"
        )
    identifier: exp.Expression = key_expression.this
    if not isinstance(identifier, exp.Identifier) or identifier.this != REF_TYPE_KEYWORD:
        raise PipelineCompileError(
            "__ref(...) optional second argument must use the ref_type keyword"
        )

    value_expression: exp.Expression = ref_type_expression.expression
    if isinstance(value_expression, exp.Literal) and value_expression.is_string:
        ref_type: str = value_expression.this
    elif isinstance(value_expression, exp.Column):
        value_identifier: exp.Expression = value_expression.this
        if not isinstance(value_identifier, exp.Identifier):
            raise PipelineCompileError("__ref(...) ref_type value must be 'reference' or 'mutable'")
        ref_type = value_identifier.this
    else:
        raise PipelineCompileError("__ref(...) ref_type value must be 'reference' or 'mutable'")

    if ref_type not in {RefType.REFERENCE, RefType.MUTABLE}:
        raise PipelineCompileError("__ref(...) ref_type value must be 'reference' or 'mutable'")

    return RefType(ref_type)
