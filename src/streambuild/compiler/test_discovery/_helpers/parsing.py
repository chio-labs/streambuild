"""Parsing helpers for authored SQL-native test files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import yaml
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from streambuild.compiler.macros.main._expand_macro_calls import expand_project_sql_macros
from streambuild.compiler.shared.models import LoadedSqlTest, SqlTestCte, SqlTestMock
from streambuild.compiler.test_discovery.constants import (
    CEREMONIAL_SELECT_LITERAL,
    EXPECTED_CTE_PREFIX,
    REF_CTE_PREFIX,
    RESERVED_SQL_TEST_CTE_NAMES,
    SOURCE_CTE_PREFIX,
    TEST_HEADER_NAME_KEY,
    TEST_HEADER_ONLY_PATTERN,
    TEST_HEADER_PATTERN,
)
from streambuild.compiler.test_discovery.exceptions import SqlTestParseError
from streambuild.spec.types import SqlRelationType


def parse_sql_test_file(file_path: Path) -> tuple[LoadedSqlTest, ...]:
    """Parse one authored SQL test file into one or more discovered test cases."""

    contents: str = file_path.read_text(encoding="utf-8")
    raw_test_blocks: tuple[str, ...] = _split_sql_test_blocks(
        file_path=file_path, contents=contents
    )
    if not raw_test_blocks:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header "
            "as the first non-whitespace content"
        )
    loaded_tests: list[LoadedSqlTest] = []
    raw_test_block: str
    for test_index, raw_test_block in enumerate(raw_test_blocks, start=1):
        loaded_tests.append(
            _parse_single_sql_test_block(
                file_path=file_path,
                raw_test_block=raw_test_block,
                test_index=test_index,
            )
        )
    _validate_test_names(file_path=file_path, loaded_tests=tuple(loaded_tests))
    return tuple(loaded_tests)


def _parse_single_sql_test_block(
    *,
    file_path: Path,
    raw_test_block: str,
    test_index: int,
) -> LoadedSqlTest:
    header_match: re.Match[str] | None = TEST_HEADER_PATTERN.match(raw_test_block)
    if header_match is None:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )
    test_name: str | None = _parse_test_name(
        file_path=file_path,
        header_contents=header_match.group("header"),
    )
    body: str = expand_project_sql_macros(
        sql=header_match.group("sql").strip(),
        file_path=file_path,
    )
    if not body:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must define mock CTEs and end with `SELECT 1`"
        )

    statement: exp.Select = _parse_single_top_level_select(file_path=file_path, sql=body)
    _validate_ceremonial_select(file_path=file_path, statement=statement)
    with_expression: exp.With | None = cast(exp.With | None, statement.args.get("with_"))
    if with_expression is None or not with_expression.expressions:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must declare mock CTEs and one "
            "__expected__<model> CTE before `SELECT 1`"
        )

    authored_ctes: list[SqlTestCte] = []
    mocks: list[SqlTestMock] = []
    expected_targets: list[SqlTestCte] = []
    seen_cte_names: set[str] = set()
    cte: exp.CTE
    for cte in with_expression.expressions:
        cte_name: str = cte.alias_or_name
        cte_query: str = cte.this.sql(dialect="clickhouse")
        if cte_name in seen_cte_names:
            raise SqlTestParseError(f"SQL test '{file_path}' defines duplicate CTE '{cte_name}'")
        seen_cte_names.add(cte_name)
        if cte_name.startswith(REF_CTE_PREFIX):
            authored_ctes.append(SqlTestCte(name=cte_name, query=cte_query))
            mocks.append(
                SqlTestMock(
                    cte_name=cte_name,
                    name=cte_name.removeprefix(REF_CTE_PREFIX),
                    relation_type=SqlRelationType.REF,
                    query=cte_query,
                )
            )
            continue
        if cte_name.startswith(SOURCE_CTE_PREFIX):
            authored_ctes.append(SqlTestCte(name=cte_name, query=cte_query))
            mocks.append(
                SqlTestMock(
                    cte_name=cte_name,
                    name=cte_name.removeprefix(SOURCE_CTE_PREFIX),
                    relation_type=SqlRelationType.SOURCE,
                    query=cte_query,
                )
            )
            continue
        if cte_name.startswith(EXPECTED_CTE_PREFIX):
            expected_model_name: str = cte_name.removeprefix(EXPECTED_CTE_PREFIX)
            if not expected_model_name:
                raise SqlTestParseError(
                    f"SQL test '{file_path}' must use __expected__<model> "
                    "to identify the target model"
                )
            expected_targets.append(SqlTestCte(name=cte_name, query=cte_query))
            continue
        if cte_name in RESERVED_SQL_TEST_CTE_NAMES:
            raise SqlTestParseError(
                f"SQL test '{file_path}' uses reserved helper CTE name '{cte_name}'"
            )
        authored_ctes.append(SqlTestCte(name=cte_name, query=cte_query))

    if not mocks:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must define at least one __ref__* or __source__* mock CTE"
        )
    if not expected_targets:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must define at least one __expected__<model> CTE"
        )
    return LoadedSqlTest(
        file_path=file_path,
        test_index=test_index,
        authored_ctes=tuple(authored_ctes),
        mocks=tuple(mocks),
        expected_targets=tuple(expected_targets),
        name=test_name,
    )


def _split_sql_test_blocks(*, file_path: Path, contents: str) -> tuple[str, ...]:
    matches: tuple[re.Match[str], ...] = tuple(TEST_HEADER_ONLY_PATTERN.finditer(contents))
    if not matches:
        return ()
    if contents[: matches[0].start()].strip():
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )
    raw_blocks: list[str] = []
    match_index: int
    match: re.Match[str]
    for match_index, match in enumerate(matches):
        next_start: int = (
            matches[match_index + 1].start() if match_index + 1 < len(matches) else len(contents)
        )
        raw_blocks.append(contents[match.start() : next_start].strip())
    return tuple(raw_blocks)


def _parse_test_name(*, file_path: Path, header_contents: str) -> str | None:
    stripped_header_contents: str = header_contents.strip()
    if not stripped_header_contents:
        return None
    try:
        parsed_header: object = yaml.safe_load(f"{{{stripped_header_contents}}}")
    except yaml.YAMLError as error:
        raise SqlTestParseError(
            f"TEST() header in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(parsed_header, dict):
        raise SqlTestParseError(
            f"TEST() header in '{file_path}' must be a mapping like `TEST (name: \"...\");`"
        )
    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in parsed_header if key != TEST_HEADER_NAME_KEY
    )
    if unsupported_keys:
        raise SqlTestParseError(
            f"TEST() in '{file_path}' only supports `name` right now; unsupported keys: "
            f"{', '.join(unsupported_keys)}"
        )
    name_value: object = parsed_header.get("name")
    if name_value is None:
        return None
    if not isinstance(name_value, str) or not name_value.strip():
        raise SqlTestParseError(f"TEST() name in '{file_path}' must be a non-empty string")
    return name_value.strip()


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
        assert loaded_test.name is not None
        if loaded_test.name in seen_names:
            raise SqlTestParseError(
                f"SQL test '{file_path}' defines duplicate TEST() name '{loaded_test.name}'"
            )
        seen_names.add(loaded_test.name)


def _parse_single_top_level_select(*, file_path: Path, sql: str) -> exp.Select:
    try:
        parsed_statements: list[exp.Expr | None] = parse(sql, read="clickhouse")
    except ParseError as error:
        raise SqlTestParseError(f"SQL test '{file_path}' could not be parsed: {error}") from error
    statements: tuple[exp.Expr, ...] = tuple(
        statement for statement in parsed_statements if statement is not None
    )
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise SqlTestParseError(
            f"SQL test '{file_path}' must contain exactly one top-level "
            "SELECT statement after TEST()"
        )
    return statements[0]


def _validate_ceremonial_select(*, file_path: Path, statement: exp.Select) -> None:
    if statement.args.get("from") is not None or statement.args.get("where") is not None:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must end with a ceremonial top-level `SELECT 1` after its CTEs"
        )
    if len(statement.expressions) != 1:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must end with a ceremonial top-level `SELECT 1` after its CTEs"
        )
    expression: exp.Expression = statement.expressions[0]
    if not isinstance(expression, exp.Literal) or expression.this != CEREMONIAL_SELECT_LITERAL:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must end with a ceremonial top-level `SELECT 1` after its CTEs"
        )
