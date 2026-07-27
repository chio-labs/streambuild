"""Expansion helpers for authored Python SQL macros."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping
from pathlib import Path

from streambuild.compiler.macros.constants import (
    MACRO_CALL_SIGIL,
    MACRO_CONTEXT_ANNOTATION_NAME,
    MACRO_CONTEXT_PARAMETER_NAME,
    MACRO_SIGIL,
    OPEN_PAREN,
    PYTHON_LITERAL_NAMES,
    UNDERSCORE,
)
from streambuild.compiler.macros.exceptions import MacroError
from streambuild.compiler.macros.models import LoadedMacro, MacroContext, MacroRegistry
from streambuild.compiler.sql_analysis.classes.sql_lexical_scanner import SqlLexicalScanner
from streambuild.diagnostics.models import RelatedDiagnosticLocation, SourceLocation


def expand_sql_body_macros(
    *,
    sql: str,
    file_path: Path,
    registry: MacroRegistry,
    context: MacroContext,
    source_line: int,
    source_column: int,
) -> str:
    """Expand authored Python macros in a SQL body string."""

    if MACRO_SIGIL not in sql:
        return sql
    rendered_sql_parts: list[str] = []
    cursor: int = 0
    while cursor < len(sql):
        macro_start_index: int | None = _find_next_macro_start(sql=sql, start_index=cursor)
        if macro_start_index is None:
            rendered_sql_parts.append(sql[cursor:])
            break
        rendered_sql_parts.append(sql[cursor:macro_start_index])
        evaluated_result: object
        evaluated_result, next_index = _evaluate_macro_call(
            sql=sql,
            call_start_index=macro_start_index,
            file_path=file_path,
            loaded_macros=registry.macros,
            context=context,
            top_level=True,
            source_line=source_line,
            source_column=source_column,
        )
        macro_result: str = str(evaluated_result)
        unexpanded_index: int | None = _find_next_macro_start(sql=macro_result, start_index=0)
        if unexpanded_index is not None:
            unexpanded_name: str = _parse_macro_name(
                sql=macro_result,
                call_start_index=unexpanded_index,
            )
            raise MacroError(
                f"Macro expansion in '{file_path}' produced output containing unexpanded macro "
                f"call '@{unexpanded_name}('. Compose macros in Python instead.",
                location=_sql_location(
                    sql=sql,
                    index=macro_start_index,
                    file_path=file_path,
                    source_line=source_line,
                    source_column=source_column,
                ),
            )
        rendered_sql_parts.append(macro_result)
        cursor = next_index
    return "".join(rendered_sql_parts)


def _evaluate_macro_call(
    *,
    sql: str,
    call_start_index: int,
    file_path: Path,
    loaded_macros: Mapping[str, LoadedMacro],
    context: MacroContext,
    top_level: bool,
    source_line: int,
    source_column: int,
) -> tuple[object, int]:
    macro_name: str = _parse_macro_name(sql=sql, call_start_index=call_start_index)
    call_location: SourceLocation = _sql_location(
        sql=sql,
        index=call_start_index,
        file_path=file_path,
        source_line=source_line,
        source_column=source_column,
    )
    loaded_macro: LoadedMacro | None = loaded_macros.get(macro_name)
    if loaded_macro is None:
        available_macro_names: str = ", ".join(sorted(loaded_macros)) or "none"
        raise MacroError(
            f"Unknown macro '@{macro_name}' in '{file_path}'. Available macros: "
            f"{available_macro_names}",
            location=call_location,
        )
    opening_paren_index: int = _skip_whitespace(
        sql=sql, start_index=call_start_index + 1 + len(macro_name)
    )
    closing_paren_index: int = _find_matching_paren(
        sql=sql, opening_paren_index=opening_paren_index
    )
    args_source: str = sql[opening_paren_index + 1 : closing_paren_index]
    try:
        args, kwargs = _parse_macro_arguments(
            args_source=args_source,
            file_path=file_path,
            loaded_macros=loaded_macros,
            context=context,
            source_line=source_line,
            source_column=source_column,
        )
    except MacroError as error:
        raise _locate_macro_error(
            error=error,
            call_location=call_location,
            loaded_macro=loaded_macro,
        ) from error
    try:
        macro_result: object = _call_loaded_macro(
            loaded_macro=loaded_macro,
            context=context,
            args=args,
            kwargs=kwargs,
            file_path=file_path,
            call_location=call_location,
        )
    except MacroError:
        raise
    except TypeError as error:
        raise MacroError(
            f"Macro '@{macro_name}' in '{file_path}' could not be called: {error}",
            location=call_location,
            related_locations=_definition_related_location(loaded_macro),
        ) from error
    except Exception as error:
        raise MacroError(
            f"Macro '@{macro_name}' in '{file_path}' failed: {error}",
            location=call_location,
            related_locations=_definition_related_location(loaded_macro),
        ) from error
    if top_level and not isinstance(macro_result, str):
        raise MacroError(
            f"Macro '@{macro_name}' in '{file_path}' must return a SQL string when "
            "used directly in SQL",
            location=call_location,
            related_locations=_definition_related_location(loaded_macro),
        )
    if not top_level:
        try:
            _validate_nested_macro_result(result=macro_result, file_path=file_path)
        except MacroError as error:
            raise _locate_macro_error(
                error=error,
                call_location=call_location,
                loaded_macro=loaded_macro,
            ) from error
    return macro_result, closing_paren_index + 1


def _parse_macro_arguments(
    *,
    args_source: str,
    file_path: Path,
    loaded_macros: Mapping[str, LoadedMacro],
    context: MacroContext,
    source_line: int,
    source_column: int,
) -> tuple[tuple[object, ...], dict[str, object]]:
    if not args_source.strip():
        return (), {}
    rewritten_args_source, placeholder_values = _rewrite_nested_macro_calls(
        args_source=args_source,
        file_path=file_path,
        loaded_macros=loaded_macros,
        context=context,
        source_line=source_line,
        source_column=source_column,
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
        if keyword.arg in kwargs:
            raise MacroError(f"Macro arguments in '{file_path}' repeat keyword '{keyword.arg}'")
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
    loaded_macros: Mapping[str, LoadedMacro],
    context: MacroContext,
    source_line: int,
    source_column: int,
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
            context=context,
            top_level=False,
            source_line=source_line,
            source_column=source_column,
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
        if node.value is None or isinstance(node.value, str | bool | int | float):
            return node.value
        raise MacroError(f"Macro arguments in '{file_path}' use an unsupported literal value")
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
        return _evaluate_dict_ast_node(
            node=node,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand: object = _evaluate_literal_ast_node(
            node=node.operand,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
        if isinstance(operand, bool) or not isinstance(operand, int | float):
            raise MacroError(f"Macro arguments in '{file_path}' use unsupported unary value")
        return -operand if isinstance(node.op, ast.USub) else operand
    raise MacroError(
        f"Macro arguments in '{file_path}' must use only Python literals and nested macro calls"
    )


def _evaluate_dict_ast_node(
    *, node: ast.Dict, placeholder_values: dict[str, object], file_path: Path
) -> dict[object, object]:
    evaluated: dict[object, object] = {}
    key_node: ast.expr | None
    value_node: ast.expr
    for key_node, value_node in zip(node.keys, node.values, strict=True):
        if key_node is None:
            raise MacroError(f"Macro arguments in '{file_path}' must not use dictionary unpacking")
        key: object = _evaluate_literal_ast_node(
            node=key_node,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
        if key is not None and not isinstance(key, str | bool | int | float):
            raise MacroError(f"Macro arguments in '{file_path}' use an unsupported dictionary key")
        evaluated[key] = _evaluate_literal_ast_node(
            node=value_node,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
    return evaluated


def _find_next_macro_start(*, sql: str, start_index: int) -> int | None:
    index: int | None = SqlLexicalScanner.find_next_unquoted_character(
        sql=sql,
        character=MACRO_CALL_SIGIL,
        start=start_index,
    )
    while index is not None:
        if _is_macro_call_start(sql=sql, at_index=index):
            return index
        index = SqlLexicalScanner.find_next_unquoted_character(
            sql=sql,
            character=MACRO_CALL_SIGIL,
            start=index + 1,
        )
    return None


def _is_macro_call_start(*, sql: str, at_index: int) -> bool:
    if at_index > 0 and _is_identifier_continue(sql[at_index - 1]):
        return False
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
    try:
        return SqlLexicalScanner.find_matching_parenthesis(
            sql=sql,
            open_index=opening_paren_index,
            context="Macro call",
        )
    except Exception as error:
        raise MacroError(str(error)) from error


def _skip_whitespace(*, sql: str, start_index: int) -> int:
    index: int = start_index
    while index < len(sql) and sql[index].isspace():
        index += 1
    return index


def _is_identifier_start(character: str) -> bool:
    return character == UNDERSCORE or character.isalpha()


def _is_identifier_continue(character: str) -> bool:
    return character == UNDERSCORE or character.isalnum()


def _call_loaded_macro(
    *,
    loaded_macro: LoadedMacro,
    context: MacroContext,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    file_path: Path,
    call_location: SourceLocation,
) -> object:
    parameters: tuple[inspect.Parameter, ...] = tuple(
        inspect.signature(loaded_macro.function).parameters.values()
    )
    accepts_context: bool = bool(parameters) and parameters[0].name == MACRO_CONTEXT_PARAMETER_NAME
    if MACRO_CONTEXT_PARAMETER_NAME in kwargs:
        raise MacroError(
            f"Macro '@{loaded_macro.name}' in '{file_path}' reserves keyword 'ctx'",
            location=call_location,
            related_locations=_definition_related_location(loaded_macro),
        )
    if not accepts_context:
        return loaded_macro.function(*args, **kwargs)
    annotation: object = parameters[0].annotation
    if annotation not in {MacroContext, MACRO_CONTEXT_ANNOTATION_NAME}:
        raise MacroError(
            f"Macro '@{loaded_macro.name}' in '{loaded_macro.file_path}' must annotate ctx "
            "as MacroContext",
            location=call_location,
            related_locations=_definition_related_location(loaded_macro),
        )
    return loaded_macro.function(context, *args, **kwargs)


def _validate_nested_macro_result(*, result: object, file_path: Path) -> None:
    if result is None or isinstance(result, str | bool | int | float):
        return
    if isinstance(result, list | tuple):
        item: object
        for item in result:
            _validate_nested_macro_result(result=item, file_path=file_path)
        return
    if isinstance(result, dict):
        key: object
        value: object
        for key, value in result.items():
            if key is not None and not isinstance(key, str | bool | int | float):
                raise MacroError(
                    f"Nested macro result in '{file_path}' contains an unsupported dictionary key"
                )
            _validate_nested_macro_result(result=value, file_path=file_path)
        return
    raise MacroError(f"Nested macro result in '{file_path}' uses an unsupported literal value")


def _sql_location(
    *, sql: str, index: int, file_path: Path, source_line: int, source_column: int
) -> SourceLocation:
    relative_line: int = sql.count("\n", 0, index)
    previous_newline: int = sql.rfind("\n", 0, index)
    relative_column: int = index - previous_newline
    return SourceLocation(
        path=file_path,
        line=source_line + relative_line,
        column=(source_column + relative_column - 1 if relative_line == 0 else relative_column),
    )


def _definition_related_location(
    loaded_macro: LoadedMacro,
) -> tuple[RelatedDiagnosticLocation, ...]:
    return (
        RelatedDiagnosticLocation(
            label="macro definition",
            location=SourceLocation(
                path=loaded_macro.file_path,
                line=loaded_macro.definition_line,
                column=1,
            ),
        ),
    )


def _locate_macro_error(
    *, error: MacroError, call_location: SourceLocation, loaded_macro: LoadedMacro
) -> MacroError:
    if error.location is not None:
        return error
    return MacroError(
        str(error),
        location=call_location,
        related_locations=_definition_related_location(loaded_macro),
    )
