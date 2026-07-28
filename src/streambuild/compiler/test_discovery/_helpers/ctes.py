"""Apache-2.0: SQLBuild compile/_helpers/sql_tests/core.py scanner@7e3b2f854f05."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.sql_analysis.classes.sql_lexical_scanner import SqlLexicalScanner
from streambuild.compiler.sql_analysis.constants import SQL_STATEMENT_DELIMITER
from streambuild.compiler.sql_analysis.exceptions import (
    SqlAnalysisError,
    SqlMissingWithClauseError,
)
from streambuild.compiler.sql_analysis.models import SqlTopLevelCtes
from streambuild.compiler.test_discovery.constants import (
    CEREMONIAL_SELECT_KEYWORD,
    CEREMONIAL_SELECT_LITERAL,
    SQL_TEST_SCANNER_CONTEXT,
)
from streambuild.compiler.test_discovery.exceptions import SqlTestParseError
from streambuild.compiler.test_discovery.models import SqlTestCte


def extract_sql_test_ctes(*, sql: str, file_path: Path) -> tuple[SqlTestCte, ...]:
    """Scan one authored test body into its top-level CTEs."""

    top_level: SqlTopLevelCtes = _scan_top_level_ctes(sql=sql, file_path=file_path)
    _validate_ceremonial_select(sql=top_level.trailing_sql, file_path=file_path)
    return tuple(SqlTestCte(name=cte.name, query=cte.query) for cte in top_level.ctes)


def _scan_top_level_ctes(*, sql: str, file_path: Path) -> SqlTopLevelCtes:
    try:
        return SqlLexicalScanner.extract_top_level_ctes(sql=sql, context=SQL_TEST_SCANNER_CONTEXT)
    except SqlMissingWithClauseError as error:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must declare mock CTEs and one "
            "__expected__<model> CTE before `SELECT 1`"
        ) from error
    except SqlAnalysisError as error:
        detail: str = str(error).removeprefix(f"{SQL_TEST_SCANNER_CONTEXT} ")
        raise SqlTestParseError(f"SQL test '{file_path}' {detail}") from error


def _validate_ceremonial_select(*, sql: str, file_path: Path) -> None:
    index: int = SqlLexicalScanner.skip_trivia(sql=sql, start=0)
    select_end: int | None = SqlLexicalScanner.try_consume_keyword(
        sql=sql, start=index, keyword=CEREMONIAL_SELECT_KEYWORD
    )
    if select_end is None:
        raise SqlTestParseError(_ceremonial_select_error(file_path))
    index = SqlLexicalScanner.skip_trivia(sql=sql, start=select_end)
    literal_end: int = index + len(CEREMONIAL_SELECT_LITERAL)
    if sql[index:literal_end] != CEREMONIAL_SELECT_LITERAL:
        raise SqlTestParseError(_ceremonial_select_error(file_path))
    index = SqlLexicalScanner.skip_trivia(sql=sql, start=literal_end)
    if index < len(sql) and sql[index] == SQL_STATEMENT_DELIMITER:
        index = SqlLexicalScanner.skip_trivia(sql=sql, start=index + 1)
    if index != len(sql):
        raise SqlTestParseError(_ceremonial_select_error(file_path))


def _ceremonial_select_error(file_path: Path) -> str:
    return f"SQL test '{file_path}' must end with a ceremonial top-level `SELECT 1` after its CTEs"
