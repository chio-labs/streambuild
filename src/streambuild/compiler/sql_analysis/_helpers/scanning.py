"""Apache-2.0: SQLBuild sql_analysis/scanning.py and compile/refs/references.py@7e3b2f854f05."""

from __future__ import annotations

from streambuild.compiler.sql_analysis.constants import (
    MODEL_REFERENCE_FUNCTION,
    PAIRED_QUOTE_CHARACTER_COUNT,
    REFERENCE_FUNCTIONS,
    REFERENCE_TYPE_KEYWORD,
    REFERENCE_WITH_TYPE_ARGUMENT_COUNT,
    SOURCE_REFERENCE_FUNCTION,
    SQL_ARGUMENT_SEPARATOR,
    SQL_BLOCK_COMMENT_CLOSE,
    SQL_BLOCK_COMMENT_OPEN,
    SQL_CLOSE_PARENTHESIS,
    SQL_ESCAPE_CHARACTER,
    SQL_HASH_COMMENT,
    SQL_IDENTIFIER_PREFIX,
    SQL_LINE_COMMENT,
    SQL_NAMED_ARGUMENT_SEPARATOR,
    SQL_OPEN_PARENTHESIS,
    SQL_QUOTE_CHARACTERS,
    SQL_STATEMENT_DELIMITER,
    VALID_REFERENCE_ARGUMENT_COUNTS,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.models import SqlHeaderBlock, SqlReference, SqlSourceSpan
from streambuild.compiler.sql_analysis.types import RefType, SqlRelationType

_REFERENCE_CONTEXT: str = "SQL reference"


def extract_references_impl(sql: str) -> tuple[SqlReference, ...]:
    """Return logical relation references found outside comments and quoted text."""

    references: list[SqlReference] = []
    index: int = 0
    while index < len(sql):
        if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
            index = skip_block_comment(sql=sql, start=index)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = skip_quoted_text(sql=sql, start=index)
            continue
        parsed: tuple[SqlReference, int] | None = _parse_reference_at(sql=sql, start=index)
        if parsed is not None:
            references.append(parsed[0])
            index = parsed[1]
            continue
        index += 1
    return tuple(references)


def split_header_blocks(*, sql: str, keyword: str) -> tuple[SqlHeaderBlock, ...]:
    """Split line-leading extension headers while ignoring SQL literals and comments."""

    starts: list[tuple[int, int, int]] = []
    index: int = 0
    while index < len(sql):
        if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
            index = skip_block_comment(sql=sql, start=index)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = skip_quoted_text(sql=sql, start=index)
            continue
        marker: tuple[int, int, int] | None = _header_marker(sql=sql, keyword=keyword, start=index)
        if marker is not None:
            starts.append(marker)
            index = marker[2]
            continue
        index += 1
    return _build_header_blocks(sql=sql, starts=tuple(starts))


def _header_marker(*, sql: str, keyword: str, start: int) -> tuple[int, int, int] | None:
    if not sql.startswith(keyword, start) or not _line_prefix_is_whitespace(sql=sql, start=start):
        return None
    keyword_end: int = start + len(keyword)
    if keyword_end < len(sql) and (
        sql[keyword_end].isalnum() or sql[keyword_end] == SQL_IDENTIFIER_PREFIX
    ):
        return None
    open_index: int = skip_trivia(sql=sql, start=keyword_end)
    if open_index >= len(sql) or sql[open_index] != SQL_OPEN_PARENTHESIS:
        return None
    close_index: int = find_matching_parenthesis(
        sql=sql,
        open_index=open_index,
        context=f"{keyword} header",
    )
    semicolon_index: int = skip_trivia(sql=sql, start=close_index + 1)
    if semicolon_index >= len(sql) or sql[semicolon_index] != SQL_STATEMENT_DELIMITER:
        raise SqlAnalysisError(f"{keyword} header must end with a semicolon")
    return start, open_index + 1, semicolon_index + 1


def _build_header_blocks(
    *, sql: str, starts: tuple[tuple[int, int, int], ...]
) -> tuple[SqlHeaderBlock, ...]:
    blocks: list[SqlHeaderBlock] = []
    index: int
    marker_start: int
    header_start: int
    body_start: int
    for index, (marker_start, header_start, body_start) in enumerate(starts):
        next_start: int = len(sql) if index + 1 == len(starts) else starts[index + 1][0]
        close_index: int = find_matching_parenthesis(
            sql=sql,
            open_index=header_start - 1,
            context="SQL extension header",
        )
        blocks.append(
            SqlHeaderBlock(
                start=marker_start,
                body_start=body_start,
                header=sql[header_start:close_index],
                body=sql[body_start:next_start],
            )
        )
    return tuple(blocks)


def _line_prefix_is_whitespace(*, sql: str, start: int) -> bool:
    line_start: int = sql.rfind("\n", 0, start) + 1
    return not sql[line_start:start].strip()


def skip_quoted_text(*, sql: str, start: int) -> int:
    """Skip ClickHouse quoted text with doubled and backslash-escaped delimiters."""

    quote: str = sql[start]
    index: int = start + 1
    while index < len(sql):
        if sql[index] == SQL_ESCAPE_CHARACTER and index + 1 < len(sql):
            index += 2
            continue
        if sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    raise _error(
        sql=sql, message=f"{_REFERENCE_CONTEXT} contains unclosed quoted text", start=start
    )


def skip_line_comment(*, sql: str, start: int) -> int:
    """Skip one SQL line comment."""

    newline_index: int = sql.find("\n", start)
    return len(sql) if newline_index == -1 else newline_index + 1


def skip_block_comment(*, sql: str, start: int) -> int:
    """Skip one SQL block comment."""

    closing_index: int = sql.find(SQL_BLOCK_COMMENT_CLOSE, start + 2)
    if closing_index == -1:
        raise _error(
            sql=sql,
            message=f"{_REFERENCE_CONTEXT} contains an unclosed block comment",
            start=start,
        )
    return closing_index + len(SQL_BLOCK_COMMENT_CLOSE)


def find_matching_parenthesis(
    *, sql: str, open_index: int, context: str = _REFERENCE_CONTEXT
) -> int:
    """Find a matching close parenthesis while skipping comments and quoted text."""

    depth: int = 1
    index: int = open_index + 1
    while index < len(sql):
        if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
            index = skip_block_comment(sql=sql, start=index)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = skip_quoted_text(sql=sql, start=index)
            continue
        if sql[index] == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif sql[index] == SQL_CLOSE_PARENTHESIS:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise _error(sql=sql, message=f"{context} contains an unclosed parenthesis", start=open_index)


def find_next_unquoted_character(*, sql: str, character: str, start: int) -> int | None:
    """Find one character outside SQL comments and quoted text."""

    index: int = start
    while index < len(sql):
        if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
            index = skip_block_comment(sql=sql, start=index)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = skip_quoted_text(sql=sql, start=index)
            continue
        if sql[index] == character:
            return index
        index += 1
    return None


def _parse_reference_at(*, sql: str, start: int) -> tuple[SqlReference, int] | None:
    function_name: str | None = next(
        (name for name in REFERENCE_FUNCTIONS if sql.startswith(name, start)),
        None,
    )
    if function_name is None or not _has_marker_boundary(sql=sql, start=start):
        return None
    open_index: int = skip_trivia(sql=sql, start=start + len(function_name))
    if open_index >= len(sql) or sql[open_index] != SQL_OPEN_PARENTHESIS:
        return None
    close_index: int = find_matching_parenthesis(sql=sql, open_index=open_index)
    arguments: tuple[str, ...] = _split_arguments(
        sql=sql,
        start=open_index + 1,
        end=close_index,
    )
    if len(arguments) not in VALID_REFERENCE_ARGUMENT_COUNTS:
        raise _error(
            sql=sql,
            message=(
                "__source(...) and __ref(...) must contain one name argument and optional ref_type"
            ),
            start=start,
            end=close_index + 1,
        )
    name: str = _parse_name(raw_value=arguments[0], sql=sql, start=start, end=close_index + 1)
    relation_type: SqlRelationType = (
        SqlRelationType.SOURCE
        if function_name == SOURCE_REFERENCE_FUNCTION
        else SqlRelationType.REF
    )
    ref_type: RefType | None = None
    if len(arguments) == REFERENCE_WITH_TYPE_ARGUMENT_COUNT:
        if function_name != MODEL_REFERENCE_FUNCTION:
            raise _error(
                sql=sql,
                message="__source(...) must not declare ref_type",
                start=start,
                end=close_index + 1,
            )
        ref_type = _parse_ref_type(
            raw_value=arguments[1], sql=sql, start=start, end=close_index + 1
        )
    return (
        SqlReference(
            name=name,
            relation_type=relation_type,
            ref_type=ref_type,
            span=source_span(sql=sql, start=start, end=close_index + 1),
        ),
        close_index + 1,
    )


def _has_marker_boundary(*, sql: str, start: int) -> bool:
    return start == 0 or not _is_identifier_character(sql[start - 1])


def _is_identifier_start(character: str) -> bool:
    return character.isalpha() or character == SQL_IDENTIFIER_PREFIX


def _is_identifier_character(character: str) -> bool:
    return character.isalnum() or character == SQL_IDENTIFIER_PREFIX


def skip_trivia(*, sql: str, start: int) -> int:
    """Skip whitespace and SQL comments."""

    index: int = start
    while index < len(sql):
        if sql[index].isspace():
            index += 1
            continue
        if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
            index = skip_block_comment(sql=sql, start=index)
            continue
        break
    return index


def _split_arguments(*, sql: str, start: int, end: int) -> tuple[str, ...]:
    arguments: list[str] = []
    argument_start: int = start
    depth: int = 0
    index: int = start
    while index < end:
        if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
            index = skip_block_comment(sql=sql, start=index)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = skip_quoted_text(sql=sql, start=index)
            continue
        if sql[index] == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif sql[index] == SQL_CLOSE_PARENTHESIS:
            depth -= 1
        elif sql[index] == SQL_ARGUMENT_SEPARATOR and depth == 0:
            arguments.append(_argument_text(sql=sql, start=argument_start, end=index))
            argument_start = index + 1
        index += 1
    arguments.append(_argument_text(sql=sql, start=argument_start, end=end))
    if any(not argument for argument in arguments):
        raise _error(
            sql=sql,
            message="__source(...) and __ref(...) arguments must not be empty",
            start=start,
            end=end,
        )
    return tuple(arguments)


def _argument_text(*, sql: str, start: int, end: int) -> str:
    parts: list[str] = []
    index: int = start
    while index < end:
        if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
            parts.append(" ")
            index = min(skip_line_comment(sql=sql, start=index), end)
            continue
        if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
            parts.append(" ")
            index = min(skip_block_comment(sql=sql, start=index), end)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            quoted_end: int = min(skip_quoted_text(sql=sql, start=index), end)
            parts.append(sql[index:quoted_end])
            index = quoted_end
            continue
        parts.append(sql[index])
        index += 1
    return "".join(parts).strip()


def _parse_name(*, raw_value: str, sql: str, start: int, end: int) -> str:
    value: str = raw_value.strip()
    if (
        len(value) >= PAIRED_QUOTE_CHARACTER_COUNT
        and value[0] == value[-1]
        and value[0] in SQL_QUOTE_CHARACTERS
    ):
        quoted_end: int = skip_quoted_text(sql=value, start=0)
        unquoted_value: str = _unquote(value)
        if quoted_end == len(value) and unquoted_value:
            return unquoted_value
    if (
        value
        and _is_identifier_start(value[0])
        and all(_is_identifier_character(character) for character in value[1:])
    ):
        return value
    raise _error(
        sql=sql,
        message="__source(...) and __ref(...) name arguments must be a quoted string or identifier",
        start=start,
        end=end,
    )


def _unquote(value: str) -> str:
    quote: str = value[0]
    result: list[str] = []
    index: int = 1
    while index < len(value) - 1:
        if value[index] == SQL_ESCAPE_CHARACTER and index + 1 < len(value) - 1:
            result.append(value[index + 1])
            index += 2
            continue
        if value[index] == quote and index + 1 < len(value) - 1 and value[index + 1] == quote:
            result.append(quote)
            index += 2
            continue
        result.append(value[index])
        index += 1
    return "".join(result)


def _parse_ref_type(*, raw_value: str, sql: str, start: int, end: int) -> RefType:
    separator_index: int = raw_value.find(SQL_NAMED_ARGUMENT_SEPARATOR)
    if (
        separator_index < 0
        or raw_value.find(SQL_NAMED_ARGUMENT_SEPARATOR, separator_index + 1) >= 0
    ):
        raise _error(
            sql=sql,
            message=(
                "__ref(...) optional second argument must be "
                "ref_type='reference' or ref_type='mutable'"
            ),
            start=start,
            end=end,
        )
    keyword: str = raw_value[:separator_index].strip()
    if keyword != REFERENCE_TYPE_KEYWORD:
        raise _error(
            sql=sql,
            message="__ref(...) optional second argument must use the ref_type keyword",
            start=start,
            end=end,
        )
    value: str = _parse_name(
        raw_value=raw_value[separator_index + 1 :],
        sql=sql,
        start=start,
        end=end,
    )
    if value not in {RefType.REFERENCE, RefType.MUTABLE}:
        raise _error(
            sql=sql,
            message="__ref(...) ref_type value must be 'reference' or 'mutable'",
            start=start,
            end=end,
        )
    return RefType(value)


def source_span(*, sql: str, start: int, end: int) -> SqlSourceSpan:
    """Build one half-open span from character offsets."""

    line: int = sql.count("\n", 0, start) + 1
    prior_newline: int = sql.rfind("\n", 0, start)
    column: int = start + 1 if prior_newline < 0 else start - prior_newline
    end_line: int = sql.count("\n", 0, end) + 1
    end_newline: int = sql.rfind("\n", 0, end)
    end_column: int = end + 1 if end_newline < 0 else end - end_newline
    return SqlSourceSpan(
        start=start,
        end=end,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
    )


def normalized_statement_sql(sql: str) -> str:
    """Remove one terminal statement delimiter while preserving trailing trivia."""

    index: int = 0
    last_significant_index: int = -1
    while index < len(sql):
        if sql.startswith(SQL_LINE_COMMENT, index) or sql.startswith(SQL_HASH_COMMENT, index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith(SQL_BLOCK_COMMENT_OPEN, index):
            index = skip_block_comment(sql=sql, start=index)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = skip_quoted_text(sql=sql, start=index)
            last_significant_index = index - 1
            continue
        if not sql[index].isspace():
            last_significant_index = index
        index += 1
    if last_significant_index >= 0 and sql[last_significant_index] == SQL_STATEMENT_DELIMITER:
        return sql[:last_significant_index] + sql[last_significant_index + 1 :]
    return sql


def _error(*, sql: str, message: str, start: int, end: int | None = None) -> SqlAnalysisError:
    return SqlAnalysisError(
        message,
        span=source_span(sql=sql, start=start, end=len(sql) if end is None else end),
    )
