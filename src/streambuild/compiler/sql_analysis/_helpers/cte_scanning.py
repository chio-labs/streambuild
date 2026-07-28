"""Apache-2.0: SQLBuild compile/_helpers/sql_tests/core.py scanner@7e3b2f854f05."""

from __future__ import annotations

from streambuild.compiler.sql_analysis._helpers.scanning import (
    find_matching_parenthesis,
    skip_trivia,
    source_span,
)
from streambuild.compiler.sql_analysis.constants import (
    SQL_ARGUMENT_SEPARATOR,
    SQL_AS_KEYWORD,
    SQL_IDENTIFIER_PREFIX,
    SQL_OPEN_PARENTHESIS,
    SQL_RECURSIVE_KEYWORD,
    SQL_WITH_KEYWORD,
)
from streambuild.compiler.sql_analysis.exceptions import (
    SqlAnalysisError,
    SqlMissingWithClauseError,
)
from streambuild.compiler.sql_analysis.models import (
    SqlCommonTableExpression,
    SqlTopLevelCtes,
)


def extract_top_level_ctes_impl(*, sql: str, context: str) -> SqlTopLevelCtes:
    """Scan one leading WITH clause and return its CTEs plus the trailing statement."""

    index: int = _consume_with_clause_start(sql=sql, context=context)
    ctes: list[SqlCommonTableExpression] = []
    seen_names: set[str] = set()
    while True:
        cte: SqlCommonTableExpression
        cte, index = _read_cte(sql=sql, start=index, context=context)
        if cte.name in seen_names:
            raise _error(
                sql=sql,
                message=f"{context} defines duplicate CTE '{cte.name}'",
                start=cte.span.start,
            )
        seen_names.add(cte.name)
        ctes.append(cte)
        index = skip_trivia(sql=sql, start=index)
        if index < len(sql) and sql[index] == SQL_ARGUMENT_SEPARATOR:
            index = skip_trivia(sql=sql, start=index + 1)
            continue
        break
    return SqlTopLevelCtes(
        ctes=tuple(ctes),
        trailing_sql=sql[index:].strip(),
        trailing_span=source_span(sql=sql, start=index, end=len(sql)),
    )


def try_consume_keyword_impl(*, sql: str, start: int, keyword: str) -> int | None:
    """Consume one case-insensitive keyword bounded by a non-identifier character."""

    end: int = start + len(keyword)
    if sql[start:end].upper() != keyword.upper():
        return None
    if end < len(sql) and _is_identifier_character(sql[end]):
        return None
    return end


def read_identifier_impl(*, sql: str, start: int, context: str) -> tuple[str, int]:
    """Read one bare SQL identifier beginning at an index."""

    index: int = start
    if index >= len(sql) or not _is_identifier_start(sql[index]):
        raise _error(sql=sql, message=f"{context} expected a CTE name", start=start)
    while index < len(sql) and _is_identifier_character(sql[index]):
        index += 1
    return sql[start:index], index


def _consume_with_clause_start(*, sql: str, context: str) -> int:
    index: int = skip_trivia(sql=sql, start=0)
    with_end: int | None = try_consume_keyword_impl(sql=sql, start=index, keyword=SQL_WITH_KEYWORD)
    if with_end is None:
        raise SqlMissingWithClauseError(
            context=context, span=source_span(sql=sql, start=index, end=len(sql))
        )
    index = skip_trivia(sql=sql, start=with_end)
    recursive_end: int | None = try_consume_keyword_impl(
        sql=sql, start=index, keyword=SQL_RECURSIVE_KEYWORD
    )
    if recursive_end is None:
        return index
    return skip_trivia(sql=sql, start=recursive_end)


def _read_cte(*, sql: str, start: int, context: str) -> tuple[SqlCommonTableExpression, int]:
    name: str
    index: int
    name, index = read_identifier_impl(sql=sql, start=start, context=context)
    index = skip_trivia(sql=sql, start=index)
    index = _skip_column_alias_list(sql=sql, start=index, context=context)
    as_end: int | None = try_consume_keyword_impl(sql=sql, start=index, keyword=SQL_AS_KEYWORD)
    if as_end is None:
        raise _error(sql=sql, message=f"{context} CTE '{name}' must use AS (...)", start=start)
    body_open: int = skip_trivia(sql=sql, start=as_end)
    if body_open >= len(sql) or sql[body_open] != SQL_OPEN_PARENTHESIS:
        raise _error(sql=sql, message=f"{context} CTE '{name}' must use AS (...)", start=start)
    body_close: int = find_matching_parenthesis(sql=sql, open_index=body_open, context=context)
    return (
        SqlCommonTableExpression(
            name=name,
            query=sql[body_open + 1 : body_close].strip(),
            span=source_span(sql=sql, start=body_open + 1, end=body_close),
        ),
        body_close + 1,
    )


def _skip_column_alias_list(*, sql: str, start: int, context: str) -> int:
    if start >= len(sql) or sql[start] != SQL_OPEN_PARENTHESIS:
        return start
    close_index: int = find_matching_parenthesis(sql=sql, open_index=start, context=context)
    return skip_trivia(sql=sql, start=close_index + 1)


def _is_identifier_start(character: str) -> bool:
    return character.isalpha() or character == SQL_IDENTIFIER_PREFIX


def _is_identifier_character(character: str) -> bool:
    return character.isalnum() or character == SQL_IDENTIFIER_PREFIX


def _error(*, sql: str, message: str, start: int) -> SqlAnalysisError:
    return SqlAnalysisError(message, span=source_span(sql=sql, start=start, end=len(sql)))
