"""Locate outer SELECT projections without interpreting SQL semantics."""

from streambuild.compiler.sql_analysis._helpers.scanning import (
    skip_block_comment,
    skip_line_comment,
    skip_quoted_text,
    source_span,
)
from streambuild.compiler.sql_analysis.constants import (
    SQL_ARGUMENT_SEPARATOR,
    SQL_BLOCK_COMMENT_OPEN,
    SQL_CLOSE_PARENTHESIS,
    SQL_HASH_COMMENT,
    SQL_IDENTIFIER_PREFIX,
    SQL_LINE_COMMENT,
    SQL_OPEN_PARENTHESIS,
    SQL_QUOTE_CHARACTERS,
    SQL_WILDCARD,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.models import SqlSourceSpan

_SELECT_KEYWORD: str = "select"
_FROM_KEYWORD: str = "from"


def outer_projection_spans(sql: str) -> tuple[SqlSourceSpan, ...]:
    """Return trimmed source spans for the outer SELECT projection list."""

    projection_start: int | None = None
    projection_end: int = len(sql)
    depth: int = 0
    index: int = 0
    while index < len(sql):
        skipped_index: int | None = _skipped_index(sql=sql, index=index)
        if skipped_index is not None:
            index = skipped_index
            continue
        character: str = sql[index]
        if character == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif character == SQL_CLOSE_PARENTHESIS:
            depth -= 1
        elif depth == 0 and _keyword_at(sql=sql, index=index, keyword=_SELECT_KEYWORD):
            projection_start = index + len(_SELECT_KEYWORD)
            index = projection_start
            continue
        elif (
            depth == 0
            and projection_start is not None
            and _keyword_at(sql=sql, index=index, keyword=_FROM_KEYWORD)
        ):
            projection_end = index
            break
        index += 1
    if projection_start is None:
        raise SqlAnalysisError("Outer SELECT projection list could not be located")
    return _split_projection_spans(
        sql=sql,
        start=projection_start,
        end=projection_end,
    )


def outer_star_span(*, sql: str, projection_span: SqlSourceSpan) -> SqlSourceSpan:
    """Return the outer wildcard token span within one projection."""

    depth: int = 0
    index: int = projection_span.start
    while index < projection_span.end:
        skipped_index: int | None = _skipped_index(sql=sql, index=index)
        if skipped_index is not None:
            index = skipped_index
            continue
        character: str = sql[index]
        if character == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif character == SQL_CLOSE_PARENTHESIS:
            depth -= 1
        elif character == SQL_WILDCARD and depth == 0:
            return source_span(sql=sql, start=index, end=index + 1)
        index += 1
    return projection_span


def outer_double_colon_type(*, sql: str, projection_span: SqlSourceSpan) -> str | None:
    """Return the authored outer double-colon cast type, if present."""

    depth: int = 0
    cast_index: int | None = None
    alias_index: int | None = None
    index: int = projection_span.start
    while index < projection_span.end:
        skipped_index: int | None = _skipped_index(sql=sql, index=index)
        if skipped_index is not None:
            index = skipped_index
            continue
        character: str = sql[index]
        if character == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif character == SQL_CLOSE_PARENTHESIS:
            depth -= 1
        elif depth == 0 and sql.startswith("::", index):
            cast_index = index
            index += 2
            continue
        elif (
            depth == 0
            and cast_index is not None
            and _keyword_at(sql=sql, index=index, keyword="as")
        ):
            alias_index = index
            break
        index += 1
    if cast_index is None:
        return None
    type_end: int = projection_span.end if alias_index is None else alias_index
    authored_type: str = sql[cast_index + 2 : type_end].strip()
    if not authored_type:
        raise SqlAnalysisError("Outer double-colon cast type could not be located")
    return authored_type


def _split_projection_spans(*, sql: str, start: int, end: int) -> tuple[SqlSourceSpan, ...]:
    spans: list[SqlSourceSpan] = []
    depth: int = 0
    projection_start: int = start
    index: int = start
    while index < end:
        skipped_index: int | None = _skipped_index(sql=sql, index=index)
        if skipped_index is not None:
            index = skipped_index
            continue
        character: str = sql[index]
        if character == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif character == SQL_CLOSE_PARENTHESIS:
            depth -= 1
        elif character == SQL_ARGUMENT_SEPARATOR and depth == 0:
            spans.append(_trimmed_span(sql=sql, start=projection_start, end=index))
            projection_start = index + 1
        index += 1
    spans.append(_trimmed_span(sql=sql, start=projection_start, end=end))
    return tuple(spans)


def _skipped_index(*, sql: str, index: int) -> int | None:
    if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
        return skip_line_comment(sql=sql, start=index)
    if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
        return skip_block_comment(sql=sql, start=index)
    if sql[index] in SQL_QUOTE_CHARACTERS:
        return skip_quoted_text(sql=sql, start=index)
    return None


def _keyword_at(*, sql: str, index: int, keyword: str) -> bool:
    candidate: str = sql[index : index + len(keyword)]
    previous: str = sql[index - 1] if index else " "
    next_index: int = index + len(keyword)
    following: str = sql[next_index] if next_index < len(sql) else " "
    return (
        candidate.lower() == keyword
        and not (previous.isalnum() or previous == SQL_IDENTIFIER_PREFIX)
        and not (following.isalnum() or following == SQL_IDENTIFIER_PREFIX)
    )


def _trimmed_span(*, sql: str, start: int, end: int) -> SqlSourceSpan:
    while start < end and sql[start].isspace():
        start += 1
    while end > start and sql[end - 1].isspace():
        end -= 1
    return source_span(sql=sql, start=start, end=end)
