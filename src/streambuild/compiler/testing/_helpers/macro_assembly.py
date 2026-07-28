"""Apache-2.0: SQLBuild planner/_helpers/sql_tests/assembly.py macro tests@7e3b2f854f05."""

from __future__ import annotations

from streambuild.compiler.test_discovery.models import LoadedSqlTest, SqlTestMacroPayload
from streambuild.compiler.testing._helpers.expectations import derive_column_names
from streambuild.compiler.testing.constants import (
    MACRO_ACTUAL_COLUMNS_LABEL,
    MACRO_EXPECTED_COLUMNS_LABEL,
    MACRO_TARGET_LABEL_PREFIX,
)
from streambuild.compiler.testing.exceptions import SqlTestAssemblyError
from streambuild.compiler.testing.models import SqlTestChainStep


def build_macro_target(
    *,
    loaded_test: LoadedSqlTest,
    payload: SqlTestMacroPayload,
    dialect: str,
) -> SqlTestChainStep:
    """Compare one expanded macro result against its authored expectation."""

    authored_ctes: tuple[tuple[str, str], ...] = tuple(
        (cte.name, cte.query) for cte in loaded_test.authored_ctes
    )
    expected_column_names: tuple[str, ...] = derive_column_names(
        query=payload.expected.query,
        file_path=loaded_test.file_path,
        label=MACRO_EXPECTED_COLUMNS_LABEL,
        authored_ctes=authored_ctes,
        dialect=dialect,
    )
    actual_column_names: tuple[str, ...] = derive_column_names(
        query=payload.actual.query,
        file_path=loaded_test.file_path,
        label=MACRO_ACTUAL_COLUMNS_LABEL,
        authored_ctes=authored_ctes,
        dialect=dialect,
    )
    if actual_column_names != expected_column_names:
        raise SqlTestAssemblyError(
            f"SQL test '{loaded_test.file_path}' mode 'macro' must project the same column "
            f"names in {MACRO_ACTUAL_COLUMNS_LABEL} and {MACRO_EXPECTED_COLUMNS_LABEL}; "
            f"got {', '.join(actual_column_names)} versus {', '.join(expected_column_names)}"
        )
    return SqlTestChainStep(
        target_model_name=(
            f"{MACRO_TARGET_LABEL_PREFIX}{loaded_test.name or loaded_test.file_path.stem}"
        ),
        expected_column_names=expected_column_names,
        ctes=authored_ctes,
        actual_query=payload.actual.query,
        expected_query=payload.expected.query,
    )
