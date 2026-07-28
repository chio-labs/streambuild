"""Apache-2.0: SQLBuild compile/_helpers/sql_tests/core.py macro validation@7e3b2f854f05."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.macros.main._find_macro_call_names import find_macro_call_names
from streambuild.compiler.test_discovery.constants import (
    MACRO_ACTUAL_CTE_NAME,
    MACRO_EXPECTED_CTE_NAME,
)
from streambuild.compiler.test_discovery.exceptions import SqlTestParseError
from streambuild.compiler.test_discovery.models import SqlTestCte


def validate_macro_mode_restrictions(*, ctes: tuple[SqlTestCte, ...], file_path: Path) -> None:
    """Reject macro calls outside __macro_actual__ in an unexpanded macro test."""

    cte: SqlTestCte
    for cte in ctes:
        if cte.name == MACRO_ACTUAL_CTE_NAME:
            continue
        if not find_macro_call_names(cte.query):
            continue
        if cte.name == MACRO_EXPECTED_CTE_NAME:
            raise SqlTestParseError(
                f"SQL test '{file_path}' mode 'macro' CTE {MACRO_EXPECTED_CTE_NAME} "
                "must not call macros"
            )
        raise SqlTestParseError(
            f"SQL test '{file_path}' mode 'macro' helper CTE '{cte.name}' must not call "
            f"macros; call macros only in {MACRO_ACTUAL_CTE_NAME}"
        )
