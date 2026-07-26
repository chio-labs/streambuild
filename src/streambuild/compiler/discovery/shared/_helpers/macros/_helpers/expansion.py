"""Expansion helpers for authored Python SQL macros."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from streambuild.compiler.discovery.shared._helpers.macros._helpers.registry import (
    load_project_macros,
)
from streambuild.compiler.discovery.shared._helpers.macros.constants import (
    BACKTICK,
    BLOCK_COMMENT_END,
    DOUBLE_QUOTE,
    MACRO_SIGIL,
    NEWLINE,
    OPEN_PAREN,
    PYTHON_LITERAL_NAMES,
    SINGLE_QUOTE,
    UNDERSCORE,
    UNEXPANDED_MACRO_PATTERN,
)
from streambuild.compiler.discovery.shared._helpers.macros.exceptions import MacroError
from streambuild.compiler.discovery.shared._helpers.macros.models import LoadedMacro


def expand_project_sql_macros(*, sql: str, file_path: Path) -> str:
    """Expand authored Python macros for one SQL file body."""

    return expand_sql_body_macros(
        sql=sql,
        file_path=file_path,
        loaded_macros=load_project_macros(file_path),
    )


def expand_sql_body_macros(
    *, sql: str, file_path: Path, loaded_macros: dict[str, LoadedMacro]
) -> str:
    """Expand authored Python macros in a SQL body string."""

    if not loaded_macros or MACRO_SIGIL not in sql:
        return sql
    rendered_sql_parts: list[str] = []
    cursor: int = 0
    while cursor < len(sql):
        macro_start_index: int | None = _find_next_macro_start(sql=sql, start_index=cursor)
        if macro_start_index is None:
            rendered_sql_parts.append(sql[cursor:])
            break
        rendered_sql_parts.append(sql[cursor:macro_start_index])
        macro_result, next_index = _evaluate_macro_call(
            sql=sql,
            call_start_index=macro_start_index,
            file_path=file_path,
            loaded_macros=loaded_macros,
            top_level=True,
        )
        if not isinstance(macro_result, str):
            raise MacroError(
                f"Macro '@{_parse_macro_name(sql=sql, call_start_index=macro_start_index)}' in "
                f"'{file_path}' must return a SQL string when used directly in SQL"
            )
        matched_call: re.Match[str] | None = UNEXPANDED_MACRO_PATTERN.search(macro_result)
        if matched_call is not None:
            raise MacroError(
                f"Macro expansion in '{file_path}' produced output containing unexpanded macro "
                f"call '{matched_call.group(0).rstrip()}'. Compose macros in Python instead."
            )
        rendered_sql_parts.append(macro_result)
        cursor = next_index
    return "".join(rendered_sql_parts)


def _evaluate_macro_call(
    *,
    sql: str,
    call_start_index: int,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    top_level: bool,
) -> tuple[object, int]:
    macro_name: str = _parse_macro_name(sql=sql, call_start_index=call_start_index)
    loaded_macro: LoadedMacro | None = loaded_macros.get(macro_name)
    if loaded_macro is None:
        available_macro_names: str = ", ".join(sorted(loaded_macros)) or "none"
        raise MacroError(
            f"Unknown macro '@{macro_name}' in '{file_path}'. Available macros: "
            f"{available_macro_names}"
        )
    opening_paren_index: int = _skip_whitespace(
        sql=sql, start_index=call_start_index + 1 + len(macro_name)
    )
    closing_paren_index: int = _find_matching_paren(
        sql=sql, opening_paren_index=opening_paren_index
    )
    args_source: str = sql[opening_paren_index + 1 : closing_paren_index]
    args, kwargs = _parse_macro_arguments(
        args_source=args_source,
        file_path=file_path,
        loaded_macros=loaded_macros,
    )
    try:
        macro_result: object = loaded_macro.function(*args, **kwargs)
    except TypeError as error:
        raise MacroError(
            f"Macro '@{macro_name}' in '{file_path}' could not be called: {error}"
        ) from error
    except Exception as error:
        raise MacroError(f"Macro '@{macro_name}' in '{file_path}' failed: {error}") from error
    if top_level and not isinstance(macro_result, str):
        raise MacroError(
            f"Macro '@{macro_name}' in '{file_path}' must return a SQL string when "
            "used directly in SQL"
        )
    return macro_result, closing_paren_index + 1


def _parse_macro_arguments(
    *,
    args_source: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
) -> tuple[tuple[object, ...], dict[str, object]]:
    if not args_source.strip():
        return (), {}
    rewritten_args_source, placeholder_values = _rewrite_nested_macro_calls(
        args_source=args_source,
        file_path=file_path,
        loaded_macros=loaded_macros,
    )
    try:
        expression: ast.Expression = ast.parse(f"_macro_call({rewritten_args_source})", mode="eval")
    except SyntaxError as error:
        raise MacroError(
            f"Macro arguments in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(expression.body, ast.Call):
        raise MacroError(f"Macro arguments in '{file_path}' could not be parsed")
    call_expression: ast.Call = expression.body
    args: tuple[object, ...] = tuple(
        _evaluate_literal_ast_node(
            node=argument,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
        for argument in call_expression.args
    )
    kwargs: dict[str, object] = {}
    keyword: ast.keyword
    for keyword in call_expression.keywords:
        if keyword.arg is None:
            raise MacroError(
                f"Macro arguments in '{file_path}' must not use **kwargs expansion syntax"
            )
        kwargs[keyword.arg] = _evaluate_literal_ast_node(
            node=keyword.value,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
    return args, kwargs


def _rewrite_nested_macro_calls(
    *,
    args_source: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
) -> tuple[str, dict[str, object]]:
    rewritten_parts: list[str] = []
    placeholder_values: dict[str, object] = {}
    cursor: int = 0
    replacement_index: int = 0
    while cursor < len(args_source):
        macro_start_index: int | None = _find_next_macro_start(sql=args_source, start_index=cursor)
        if macro_start_index is None:
            rewritten_parts.append(args_source[cursor:])
            break
        rewritten_parts.append(args_source[cursor:macro_start_index])
        nested_result, next_index = _evaluate_macro_call(
            sql=args_source,
            call_start_index=macro_start_index,
            file_path=file_path,
            loaded_macros=loaded_macros,
            top_level=False,
        )
        placeholder: str = f"__streambuild_macro_arg_{replacement_index}"
        replacement_index += 1
        placeholder_values[placeholder] = nested_result
        rewritten_parts.append(placeholder)
        cursor = next_index
    return "".join(rewritten_parts), placeholder_values


def _evaluate_literal_ast_node(
    *,
    node: ast.AST,
    placeholder_values: dict[str, object],
    file_path: Path,
) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in placeholder_values:
            return placeholder_values[node.id]
        if node.id in PYTHON_LITERAL_NAMES:
            return ast.literal_eval(node)
    if isinstance(node, ast.List):
        return [
            _evaluate_literal_ast_node(
                node=element,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for element in node.elts
        ]
    if isinstance(node, ast.Tuple):
        return tuple(
            _evaluate_literal_ast_node(
                node=element,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for element in node.elts
        )
    if isinstance(node, ast.Dict):
        return {
            _evaluate_literal_ast_node(
                node=key,
                placeholder_values=placeholder_values,
                file_path=file_path,
            ): _evaluate_literal_ast_node(
                node=value,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand: object = _evaluate_literal_ast_node(
            node=node.operand,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
        if not isinstance(operand, int | float):
            raise MacroError(f"Macro arguments in '{file_path}' use unsupported unary value")
        return -operand if isinstance(node.op, ast.USub) else operand
    raise MacroError(
        f"Macro arguments in '{file_path}' must use only Python literals and nested macro calls"
    )


def _find_next_macro_start(*, sql: str, start_index: int) -> int | None:
    index: int = start_index
    while index < len(sql):
        character: str = sql[index]
        if character == SINGLE_QUOTE:
            index = _skip_single_quoted_string(sql=sql, start_index=index)
            continue
        if character == DOUBLE_QUOTE:
            index = _skip_double_quoted_string(sql=sql, start_index=index)
            continue
        if character == BACKTICK:
            index = _skip_backtick_quoted_identifier(sql=sql, start_index=index)
            continue
        if sql.startswith("--", index):
            index = _skip_line_comment(sql=sql, start_index=index)
            continue
        if sql.startswith("/*", index):
            index = _skip_block_comment(sql=sql, start_index=index)
            continue
        if character == "@" and _is_macro_call_start(sql=sql, at_index=index):
            return index
        index += 1
    return None


def _is_macro_call_start(*, sql: str, at_index: int) -> bool:
    if at_index + 1 >= len(sql) or not _is_identifier_start(sql[at_index + 1]):
        return False
    cursor: int = at_index + 2
    while cursor < len(sql) and _is_identifier_continue(sql[cursor]):
        cursor += 1
    cursor = _skip_whitespace(sql=sql, start_index=cursor)
    return cursor < len(sql) and sql[cursor] == OPEN_PAREN


def _parse_macro_name(*, sql: str, call_start_index: int) -> str:
    cursor: int = call_start_index + 1
    while cursor < len(sql) and _is_identifier_continue(sql[cursor]):
        cursor += 1
    return sql[call_start_index + 1 : cursor]


def _find_matching_paren(*, sql: str, opening_paren_index: int) -> int:
    if opening_paren_index >= len(sql) or sql[opening_paren_index] != OPEN_PAREN:
        raise MacroError("expected opening parenthesis")
    depth: int = 1
    index: int = opening_paren_index + 1
    while index < len(sql):
        character: str = sql[index]
        if character == SINGLE_QUOTE:
            index = _skip_single_quoted_string(sql=sql, start_index=index)
            continue
        if character == DOUBLE_QUOTE:
            index = _skip_double_quoted_string(sql=sql, start_index=index)
            continue
        if character == BACKTICK:
            index = _skip_backtick_quoted_identifier(sql=sql, start_index=index)
            continue
        if sql.startswith("--", index):
            index = _skip_line_comment(sql=sql, start_index=index)
            continue
        if sql.startswith("/*", index):
            index = _skip_block_comment(sql=sql, start_index=index)
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise MacroError("Macro call could not be parsed: missing closing ')' ")


def _skip_whitespace(*, sql: str, start_index: int) -> int:
    index: int = start_index
    while index < len(sql) and sql[index].isspace():
        index += 1
    return index


def _skip_single_quoted_string(*, sql: str, start_index: int) -> int:
    index: int = start_index + 1
    while index < len(sql):
        if sql[index] == SINGLE_QUOTE:
            if index + 1 < len(sql) and sql[index + 1] == SINGLE_QUOTE:
                index += 2
                continue
            return index + 1
        index += 1
    return index


def _skip_double_quoted_string(*, sql: str, start_index: int) -> int:
    index: int = start_index + 1
    while index < len(sql):
        if sql[index] == DOUBLE_QUOTE:
            if index + 1 < len(sql) and sql[index + 1] == DOUBLE_QUOTE:
                index += 2
                continue
            return index + 1
        index += 1
    return index


def _skip_backtick_quoted_identifier(*, sql: str, start_index: int) -> int:
    index: int = start_index + 1
    while index < len(sql):
        if sql[index] == BACKTICK:
            return index + 1
        index += 1
    return index


def _skip_line_comment(*, sql: str, start_index: int) -> int:
    index: int = start_index + 2
    while index < len(sql) and sql[index] != NEWLINE:
        index += 1
    return index


def _skip_block_comment(*, sql: str, start_index: int) -> int:
    index: int = start_index + 2
    while index + 1 < len(sql):
        if sql[index : index + 2] == BLOCK_COMMENT_END:
            return index + 2
        index += 1
    return len(sql)


def _is_identifier_start(character: str) -> bool:
    return character == UNDERSCORE or character.isalpha()


def _is_identifier_continue(character: str) -> bool:
    return character == UNDERSCORE or character.isalnum()
