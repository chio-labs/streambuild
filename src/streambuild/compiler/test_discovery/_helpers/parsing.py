"""Parsing helpers for authored SQL-native test files."""

from __future__ import annotations

import re
from pathlib import Path

from streambuild.compiler.macros.main._expand_macro_calls import expand_macro_calls
from streambuild.compiler.macros.models import MacroContext, MacroRegistry
from streambuild.compiler.test_discovery._helpers.classification import (
    classify_macro_test_ctes,
    classify_model_test_ctes,
)
from streambuild.compiler.test_discovery._helpers.ctes import extract_sql_test_ctes
from streambuild.compiler.test_discovery._helpers.headers import parse_test_header
from streambuild.compiler.test_discovery._helpers.macro_mode import (
    validate_macro_mode_restrictions,
)
from streambuild.compiler.test_discovery.constants import (
    TEST_HEADER_ONLY_PATTERN,
    TEST_HEADER_PATTERN,
)
from streambuild.compiler.test_discovery.exceptions import SqlTestParseError
from streambuild.compiler.test_discovery.models import (
    LoadedSqlTest,
    SqlTestCte,
    SqlTestHeader,
    SqlTestMacroPayload,
    SqlTestModelPayload,
)
from streambuild.compiler.test_discovery.types import SqlTestMode


def parse_sql_test_file(
    *,
    file_path: Path,
    contents: str | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
) -> tuple[LoadedSqlTest, ...]:
    """Parse one authored SQL test file into one or more discovered test cases."""

    source_contents: str = file_path.read_text(encoding="utf-8") if contents is None else contents
    raw_test_blocks: tuple[tuple[str, int], ...] = _split_sql_test_blocks(
        file_path=file_path, contents=source_contents
    )
    if not raw_test_blocks:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header "
            "as the first non-whitespace content"
        )
    loaded_tests: list[LoadedSqlTest] = []
    raw_test_block: str
    block_start_index: int
    for test_index, (raw_test_block, block_start_index) in enumerate(raw_test_blocks, start=1):
        loaded_tests.append(
            _parse_single_sql_test_block(
                file_path=file_path,
                source_contents=source_contents,
                raw_test_block=raw_test_block,
                block_start_index=block_start_index,
                test_index=test_index,
                macro_registry=macro_registry,
                macro_context=macro_context,
            )
        )
    _validate_test_names(file_path=file_path, loaded_tests=tuple(loaded_tests))
    return tuple(loaded_tests)


def _parse_single_sql_test_block(
    *,
    file_path: Path,
    source_contents: str,
    raw_test_block: str,
    block_start_index: int,
    test_index: int,
    macro_registry: MacroRegistry | None,
    macro_context: MacroContext | None,
) -> LoadedSqlTest:
    header_match: re.Match[str] | None = TEST_HEADER_PATTERN.match(raw_test_block)
    if header_match is None:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )
    header: SqlTestHeader = parse_test_header(
        file_path=file_path,
        header_contents=header_match.group("header"),
    )
    raw_body: str = header_match.group("sql")
    body: str = _expand_test_body(
        sql=raw_body.strip(),
        file_path=file_path,
        macro_registry=macro_registry,
        macro_context=macro_context,
        source_offset=block_start_index + header_match.start("sql") + _leading_length(raw_body),
        source_contents=source_contents,
        header=header,
        raw_body=raw_body,
    )
    if not body:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must define mock CTEs and end with `SELECT 1`"
        )
    ctes: tuple[SqlTestCte, ...] = extract_sql_test_ctes(sql=body, file_path=file_path)
    return _build_loaded_test(
        file_path=file_path,
        header=header,
        ctes=ctes,
        test_index=test_index,
    )


def _build_loaded_test(
    *,
    file_path: Path,
    header: SqlTestHeader,
    ctes: tuple[SqlTestCte, ...],
    test_index: int,
) -> LoadedSqlTest:
    authored_ctes: tuple[SqlTestCte, ...]
    payload: SqlTestModelPayload | SqlTestMacroPayload
    if header.mode == SqlTestMode.MACRO:
        authored_ctes, payload = classify_macro_test_ctes(ctes=ctes, file_path=file_path)
    else:
        authored_ctes, payload = classify_model_test_ctes(ctes=ctes, file_path=file_path)
    return LoadedSqlTest(
        file_path=file_path,
        mode=header.mode,
        authored_ctes=authored_ctes,
        payload=payload,
        name=header.name,
        test_index=test_index,
    )


def _expand_test_body(
    *,
    sql: str,
    file_path: Path,
    macro_registry: MacroRegistry | None,
    macro_context: MacroContext | None,
    source_offset: int,
    source_contents: str,
    header: SqlTestHeader,
    raw_body: str,
) -> str:
    if header.mode == SqlTestMode.MACRO:
        validate_macro_mode_restrictions(
            ctes=extract_sql_test_ctes(sql=raw_body.strip(), file_path=file_path),
            file_path=file_path,
        )
    if macro_registry is None or macro_context is None:
        return sql
    source_line: int
    source_column: int
    source_line, source_column = _source_position(contents=source_contents, index=source_offset)
    return expand_macro_calls(
        sql=sql,
        file_path=file_path,
        registry=macro_registry,
        context=macro_context,
        source_line=source_line,
        source_column=source_column,
    )


def _leading_length(raw_body: str) -> int:
    return len(raw_body) - len(raw_body.lstrip())


def _split_sql_test_blocks(*, file_path: Path, contents: str) -> tuple[tuple[str, int], ...]:
    matches: tuple[re.Match[str], ...] = tuple(TEST_HEADER_ONLY_PATTERN.finditer(contents))
    if not matches:
        return ()
    if contents[: matches[0].start()].strip():
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )
    raw_blocks: list[tuple[str, int]] = []
    match_index: int
    match: re.Match[str]
    for match_index, match in enumerate(matches):
        next_start: int = (
            matches[match_index + 1].start() if match_index + 1 < len(matches) else len(contents)
        )
        raw_blocks.append((contents[match.start() : next_start].strip(), match.start()))
    return tuple(raw_blocks)


def _source_position(*, contents: str, index: int) -> tuple[int, int]:
    line: int = contents.count("\n", 0, index) + 1
    previous_newline_index: int = contents.rfind("\n", 0, index)
    return line, index - previous_newline_index


def _validate_test_names(*, file_path: Path, loaded_tests: tuple[LoadedSqlTest, ...]) -> None:
    if len(loaded_tests) <= 1:
        return
    unnamed_tests: tuple[int, ...] = tuple(
        loaded_test.test_index for loaded_test in loaded_tests if loaded_test.name is None
    )
    if unnamed_tests:
        missing_name_indexes: str = ", ".join(str(index) for index in unnamed_tests)
        raise SqlTestParseError(
            f"SQL test '{file_path}' contains multiple TEST blocks; every block must define "
            f"a unique `name`. Missing names for blocks: {missing_name_indexes}"
        )
    seen_names: set[str] = set()
    loaded_test: LoadedSqlTest
    for loaded_test in loaded_tests:
        if loaded_test.name in seen_names:
            raise SqlTestParseError(
                f"SQL test '{file_path}' defines duplicate TEST() name '{loaded_test.name}'"
            )
        seen_names.add(str(loaded_test.name))
