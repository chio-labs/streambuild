"""Chain and assertion step assembly for model-mode SQL tests."""

from __future__ import annotations

from collections.abc import Mapping

from streambuild.compiler.compile.models import CompiledModel
from streambuild.compiler.sql_analysis.main._extract_references import extract_references
from streambuild.compiler.sql_analysis.models import SqlReference
from streambuild.compiler.test_discovery.constants import (
    ASSERT_CTE_PREFIX,
    EXPECTED_CTE_PREFIX,
)
from streambuild.compiler.test_discovery.models import (
    LoadedSqlTest,
    SqlTestCte,
    SqlTestModelPayload,
)
from streambuild.compiler.testing._helpers.expectations import (
    build_typed_expected_query,
    derive_column_names,
)
from streambuild.compiler.testing.classes.sql_test_chain_assembler import SqlTestChainAssembler
from streambuild.compiler.testing.constants import (
    ASSERTION_COLUMNS_LABEL,
    EXPECTED_COLUMNS_LABEL,
)
from streambuild.compiler.testing.exceptions import SqlTestAssemblyError
from streambuild.compiler.testing.models import SqlTestAssertionStep, SqlTestChainStep


def build_chain_steps(
    *,
    loaded_test: LoadedSqlTest,
    payload: SqlTestModelPayload,
    assembler: SqlTestChainAssembler,
    authored_ctes: tuple[tuple[str, str], ...],
    dialect: str,
) -> tuple[SqlTestChainStep, ...]:
    """Assemble one comparison per authored expected target in dependency order."""

    steps: list[tuple[int, SqlTestChainStep]] = []
    expected_target: SqlTestCte
    for expected_target in payload.expected_targets:
        target_model_name: str = expected_target.name.removeprefix(EXPECTED_CTE_PREFIX)
        entry: CompiledModel | None = assembler.registry.get(target_model_name)
        if entry is None:
            raise SqlTestAssemblyError(
                f"SQL test '{loaded_test.file_path}' targets unknown model '{target_model_name}'"
            )
        actual_cte_name: str = assembler.resolve(logical_name=target_model_name)
        steps.append(
            (
                assembler.assembled_position(target_model_name),
                _build_chain_step(
                    loaded_test=loaded_test,
                    entry=entry,
                    expected_target=expected_target,
                    target_model_name=target_model_name,
                    actual_cte_name=actual_cte_name,
                    authored_ctes=authored_ctes,
                    assembler=assembler,
                    dialect=dialect,
                ),
            )
        )
    return tuple(step for _position, step in sorted(steps, key=lambda item: item[0]))


def build_assertion_steps(
    *,
    loaded_test: LoadedSqlTest,
    payload: SqlTestModelPayload,
    assembler: SqlTestChainAssembler,
    authored_ctes: tuple[tuple[str, str], ...],
    dialect: str,
) -> tuple[SqlTestAssertionStep, ...]:
    """Assemble one zero-row assertion per authored `__assert__` CTE."""

    steps: list[SqlTestAssertionStep] = []
    assertion: SqlTestCte
    for assertion in payload.assertions:
        assertion_name: str = assertion.name.removeprefix(ASSERT_CTE_PREFIX)
        resolver: dict[str, str] = {}
        reference: SqlReference
        for reference in extract_references(assertion.query):
            resolver[reference.name] = assembler.resolve(logical_name=reference.name)
        resolved_query: str = assembler.rewrite(sql=assertion.query, resolver=resolver)
        steps.append(
            SqlTestAssertionStep(
                name=assertion_name,
                column_names=derive_column_names(
                    query=resolved_query,
                    file_path=loaded_test.file_path,
                    label=f"{ASSERTION_COLUMNS_LABEL}{assertion_name}",
                    authored_ctes=(*authored_ctes, *assembler.assembled_ctes),
                    dialect=dialect,
                ),
                ctes=(*authored_ctes, *assembler.assembled_ctes),
                query=resolved_query,
            )
        )
    return tuple(steps)


def _build_chain_step(
    *,
    loaded_test: LoadedSqlTest,
    entry: CompiledModel,
    expected_target: SqlTestCte,
    target_model_name: str,
    actual_cte_name: str,
    authored_ctes: tuple[tuple[str, str], ...],
    assembler: SqlTestChainAssembler,
    dialect: str,
) -> SqlTestChainStep:
    expected_column_names: tuple[str, ...] = derive_column_names(
        query=expected_target.query,
        file_path=loaded_test.file_path,
        label=f"{EXPECTED_COLUMNS_LABEL}{target_model_name}",
        authored_ctes=authored_ctes,
        dialect=dialect,
    )
    output_column_type_by_name: Mapping[str, str] = {
        column.name: column.type for column in entry.output_columns
    }
    _reject_unknown_columns(
        loaded_test=loaded_test,
        target_model_name=target_model_name,
        expected_column_names=expected_column_names,
        output_column_type_by_name=output_column_type_by_name,
    )
    return SqlTestChainStep(
        target_model_name=target_model_name,
        expected_column_names=expected_column_names,
        ctes=(*authored_ctes, *assembler.assembled_ctes),
        actual_query=("SELECT " + ", ".join(expected_column_names) + f" FROM {actual_cte_name}"),
        expected_query=build_typed_expected_query(
            expected_query=expected_target.query,
            expected_column_names=expected_column_names,
            output_column_type_by_name=output_column_type_by_name,
        ),
    )


def _reject_unknown_columns(
    *,
    loaded_test: LoadedSqlTest,
    target_model_name: str,
    expected_column_names: tuple[str, ...],
    output_column_type_by_name: Mapping[str, str],
) -> None:
    missing_columns: tuple[str, ...] = tuple(
        column_name
        for column_name in expected_column_names
        if column_name not in output_column_type_by_name
    )
    if missing_columns:
        raise SqlTestAssemblyError(
            f"SQL test '{loaded_test.file_path}' expects columns not produced by "
            f"'{target_model_name}': {', '.join(missing_columns)}"
        )
