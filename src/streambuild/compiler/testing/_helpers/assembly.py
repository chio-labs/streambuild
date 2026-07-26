"""Assembly helpers for SQL-native test cases."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from sqlglot import exp, parse_one

from streambuild.compiler.compile.main.replace_refs import replace_refs
from streambuild.compiler.compile.models import CompiledPipeline, CompiledTransformStep
from streambuild.compiler.test_discovery.constants import EXPECTED_CTE_PREFIX
from streambuild.compiler.test_discovery.models import LoadedSqlTest, SqlTestCte
from streambuild.compiler.testing.exceptions import SqlTestAssemblyError
from streambuild.compiler.testing.models import (
    CompiledSqlTestModelEntry,
    SqlTestCase,
    SqlTestTargetCase,
)


def build_sql_test_case(
    *,
    loaded_test: LoadedSqlTest,
    compiled_pipelines: tuple[CompiledPipeline, ...],
) -> SqlTestCase:
    registry: dict[str, CompiledSqlTestModelEntry] = _build_compiled_model_registry(
        compiled_pipelines
    )
    source_names: set[str] = {
        compiled_pipeline.pipeline.source.name for compiled_pipeline in compiled_pipelines
    }
    mock_name_by_logical_name: dict[str, str] = {
        mock.name: mock.cte_name for mock in loaded_test.mocks
    }
    authored_ctes: list[tuple[str, str]] = [
        (cte.name, cte.query) for cte in loaded_test.authored_ctes
    ]
    assembled_model_ctes: list[tuple[str, str]] = []
    assembled_name_by_logical_name: dict[str, str] = {}
    in_progress: set[str] = set()

    def resolve_relation(logical_name: str) -> str:
        if logical_name in mock_name_by_logical_name:
            return mock_name_by_logical_name[logical_name]
        if logical_name in assembled_name_by_logical_name:
            return assembled_name_by_logical_name[logical_name]
        if logical_name in in_progress:
            raise SqlTestAssemblyError(
                f"SQL test '{loaded_test.file_path}' encountered a cyclic dependency "
                f"while assembling '{logical_name}'"
            )
        if logical_name not in registry:
            suggestion_prefix: str = "__source__" if logical_name in source_names else "__ref__"
            target_model_names: str = ", ".join(
                expected_target.name.removeprefix(EXPECTED_CTE_PREFIX)
                for expected_target in loaded_test.expected_targets
            )
            raise SqlTestAssemblyError(
                f"SQL test '{loaded_test.file_path}' targets "
                f"'{target_model_names}', but dependency '{logical_name}' "
                "cannot be resolved. Add "
                f"`{suggestion_prefix}{logical_name}` to mock it directly."
            )
        entry: CompiledSqlTestModelEntry = registry[logical_name]
        query: str | None = entry.compiled_transform.transform.query
        if query is None:
            raise SqlTestAssemblyError(
                f"SQL test '{loaded_test.file_path}' could not load query text "
                f"for model '{logical_name}'"
            )
        in_progress.add(logical_name)
        resolver: dict[str, str] = {
            parsed_ref.name: resolve_relation(parsed_ref.name)
            for parsed_ref in entry.compiled_transform.parsed_refs
        }
        cte_name: str = f"__model__{logical_name}"
        assembled_name_by_logical_name[logical_name] = cte_name
        assembled_model_ctes.append((cte_name, replace_refs(sql=query, resolver=resolver)))
        in_progress.remove(logical_name)
        return cte_name

    target_cases: list[SqlTestTargetCase] = []
    expected_target: SqlTestCte
    for expected_target in loaded_test.expected_targets:
        target_model_name: str = expected_target.name.removeprefix(EXPECTED_CTE_PREFIX)
        if target_model_name not in registry:
            raise SqlTestAssemblyError(
                f"SQL test '{loaded_test.file_path}' targets unknown model '{target_model_name}'"
            )
        target_entry: CompiledSqlTestModelEntry = registry[target_model_name]
        actual_cte_name: str = resolve_relation(target_model_name)
        expected_column_names: tuple[str, ...] = _derive_expected_column_names(
            query=expected_target.query,
            file_path=loaded_test.file_path,
            available_cte_queries_by_name={
                cte.name: cte.query for cte in loaded_test.authored_ctes
            },
        )
        output_column_type_by_name: Mapping[str, str] = {
            column.name: column.type
            for column in target_entry.compiled_transform.target_table.columns
        }
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
        typed_expected_query: str = _build_typed_expected_query(
            expected_query=expected_target.query,
            expected_column_names=expected_column_names,
            output_column_type_by_name=output_column_type_by_name,
        )
        actual_projection_query: str = (
            "SELECT " + ", ".join(expected_column_names) + f" FROM {actual_cte_name}"
        )
        target_case_ctes: list[tuple[str, str]] = [
            *authored_ctes,
            *assembled_model_ctes,
            ("__expected__typed", typed_expected_query),
            ("__actual__projected", actual_projection_query),
            (
                "__missing__",
                "SELECT * FROM __expected__typed EXCEPT SELECT * FROM __actual__projected",
            ),
            (
                "__unexpected__",
                "SELECT * FROM __actual__projected EXCEPT SELECT * FROM __expected__typed",
            ),
        ]
        final_query: str = (
            "WITH\n"
            + ",\n".join(
                f"{cte_name} AS (\n{cte_query}\n)" for cte_name, cte_query in target_case_ctes
            )
            + "\nSELECT 'missing' AS _diff_type, * FROM __missing__\n"
            + "UNION ALL\n"
            + "SELECT 'unexpected' AS _diff_type, * FROM __unexpected__"
        )
        target_cases.append(
            SqlTestTargetCase(
                target_model_name=target_model_name,
                expected_column_names=expected_column_names,
                query=final_query,
            )
        )
    return SqlTestCase(
        file_path=loaded_test.file_path,
        target_cases=tuple(target_cases),
        test_index=loaded_test.test_index,
        name=loaded_test.name,
    )


def _build_compiled_model_registry(
    compiled_pipelines: tuple[CompiledPipeline, ...],
) -> dict[str, CompiledSqlTestModelEntry]:
    registry: dict[str, CompiledSqlTestModelEntry] = {}
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        compiled_transform: CompiledTransformStep
        for compiled_transform in compiled_pipeline.transforms:
            registry[compiled_transform.transform.name] = CompiledSqlTestModelEntry(
                compiled_pipeline=compiled_pipeline,
                compiled_transform=compiled_transform,
            )
    return registry


def _derive_expected_column_names(
    *,
    query: str,
    file_path: Path,
    available_cte_queries_by_name: Mapping[str, str],
) -> tuple[str, ...]:
    return _infer_query_column_names(
        query=query,
        file_path=file_path,
        available_cte_queries_by_name=available_cte_queries_by_name,
        resolution_stack=(),
    )


def _infer_query_column_names(
    *,
    query: str,
    file_path: Path,
    available_cte_queries_by_name: Mapping[str, str],
    resolution_stack: tuple[str, ...],
) -> tuple[str, ...]:
    statement: exp.Expr = parse_one(query, read="clickhouse")
    if isinstance(statement, exp.Select):
        return _infer_select_column_names(
            statement=statement,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
    if isinstance(statement, exp.SetOperation):
        return _infer_set_operation_column_names(
            statement=statement,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
    if isinstance(statement, exp.Subquery):
        return _infer_expression_column_names(
            statement=statement.this,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
    raise SqlTestAssemblyError(
        f"SQL test '{file_path}' must define __expected__<model> as a SELECT query"
    )


def _infer_expression_column_names(
    *,
    statement: exp.Expression,
    file_path: Path,
    available_cte_queries_by_name: Mapping[str, str],
    resolution_stack: tuple[str, ...],
) -> tuple[str, ...]:
    if isinstance(statement, exp.Select):
        return _infer_select_column_names(
            statement=statement,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
    if isinstance(statement, exp.SetOperation):
        return _infer_set_operation_column_names(
            statement=statement,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
    if isinstance(statement, exp.Subquery):
        return _infer_expression_column_names(
            statement=statement.this,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
    raise SqlTestAssemblyError(
        f"SQL test '{file_path}' must define __expected__<model> as a SELECT query"
    )


def _infer_set_operation_column_names(
    *,
    statement: exp.SetOperation,
    file_path: Path,
    available_cte_queries_by_name: Mapping[str, str],
    resolution_stack: tuple[str, ...],
) -> tuple[str, ...]:
    left_column_names: tuple[str, ...] = _infer_expression_column_names(
        statement=statement.this,
        file_path=file_path,
        available_cte_queries_by_name=available_cte_queries_by_name,
        resolution_stack=resolution_stack,
    )
    right_expression: exp.Expression | None = statement.expression
    if right_expression is None:
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' must define __expected__<model> as a SELECT query"
        )
    right_projection_count: int = _infer_expression_projection_count(
        statement=right_expression,
        file_path=file_path,
        available_cte_queries_by_name=available_cte_queries_by_name,
        resolution_stack=resolution_stack,
    )
    if len(left_column_names) != right_projection_count:
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' must keep the same projected column count across "
            "all __expected__<model> set-operation branches"
        )
    return left_column_names


def _infer_expression_projection_count(
    *,
    statement: exp.Expression,
    file_path: Path,
    available_cte_queries_by_name: Mapping[str, str],
    resolution_stack: tuple[str, ...],
) -> int:
    if isinstance(statement, exp.Select):
        return _infer_select_projection_count(
            statement=statement,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
    if isinstance(statement, exp.SetOperation):
        left_count: int = _infer_expression_projection_count(
            statement=statement.this,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
        right_expression: exp.Expression | None = statement.expression
        if right_expression is None:
            raise SqlTestAssemblyError(
                f"SQL test '{file_path}' must define __expected__<model> as a SELECT query"
            )
        right_count: int = _infer_expression_projection_count(
            statement=right_expression,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
        if left_count != right_count:
            raise SqlTestAssemblyError(
                f"SQL test '{file_path}' must keep the same projected column count across "
                "all __expected__<model> set-operation branches"
            )
        return left_count
    if isinstance(statement, exp.Subquery):
        return _infer_expression_projection_count(
            statement=statement.this,
            file_path=file_path,
            available_cte_queries_by_name=available_cte_queries_by_name,
            resolution_stack=resolution_stack,
        )
    raise SqlTestAssemblyError(
        f"SQL test '{file_path}' must define __expected__<model> as a SELECT query"
    )


def _infer_select_projection_count(
    *,
    statement: exp.Select,
    file_path: Path,
    available_cte_queries_by_name: Mapping[str, str],
    resolution_stack: tuple[str, ...],
) -> int:
    projection_count: int = 0
    source_name_by_alias: dict[str, str] = _build_select_source_name_by_alias(statement)
    projection: exp.Expression
    for projection in statement.expressions:
        if isinstance(projection, exp.Star):
            projection_count += len(
                _expand_star_projection(
                    source_name=None,
                    statement=statement,
                    file_path=file_path,
                    available_cte_queries_by_name=available_cte_queries_by_name,
                    source_name_by_alias=source_name_by_alias,
                    resolution_stack=resolution_stack,
                )
            )
            continue
        if isinstance(projection, exp.Column) and projection.is_star:
            projection_count += len(
                _expand_star_projection(
                    source_name=projection.table,
                    statement=statement,
                    file_path=file_path,
                    available_cte_queries_by_name=available_cte_queries_by_name,
                    source_name_by_alias=source_name_by_alias,
                    resolution_stack=resolution_stack,
                )
            )
            continue
        projection_count += 1
    if projection_count == 0:
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' must define at least one projected column "
            "in __expected__<model>"
        )
    return projection_count


def _infer_select_column_names(
    *,
    statement: exp.Select,
    file_path: Path,
    available_cte_queries_by_name: Mapping[str, str],
    resolution_stack: tuple[str, ...],
) -> tuple[str, ...]:
    column_names: list[str] = []
    source_name_by_alias: dict[str, str] = _build_select_source_name_by_alias(statement)
    projection: exp.Expression
    for projection in statement.expressions:
        if isinstance(projection, exp.Alias):
            column_names.append(projection.alias)
            continue
        if isinstance(projection, exp.Column) and projection.table is None:
            column_names.append(projection.name)
            continue
        if isinstance(projection, exp.Star):
            column_names.extend(
                _expand_star_projection(
                    source_name=None,
                    statement=statement,
                    file_path=file_path,
                    available_cte_queries_by_name=available_cte_queries_by_name,
                    source_name_by_alias=source_name_by_alias,
                    resolution_stack=resolution_stack,
                )
            )
            continue
        if isinstance(projection, exp.Column) and projection.is_star:
            column_names.extend(
                _expand_star_projection(
                    source_name=projection.table,
                    statement=statement,
                    file_path=file_path,
                    available_cte_queries_by_name=available_cte_queries_by_name,
                    source_name_by_alias=source_name_by_alias,
                    resolution_stack=resolution_stack,
                )
            )
            continue
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' must alias every __expected__<model> projection, "
            "or use SELECT * from a helper/mock CTE with inferrable columns"
        )
    if not column_names:
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' must define at least one projected column "
            "in __expected__<model>"
        )
    return tuple(column_names)


def _expand_star_projection(
    *,
    source_name: str | None,
    statement: exp.Select,
    file_path: Path,
    available_cte_queries_by_name: Mapping[str, str],
    source_name_by_alias: Mapping[str, str],
    resolution_stack: tuple[str, ...],
) -> tuple[str, ...]:
    resolved_source_name: str = _resolve_star_source_name(
        source_name=source_name,
        statement=statement,
        file_path=file_path,
        source_name_by_alias=source_name_by_alias,
    )
    if resolved_source_name in resolution_stack:
        cycle_path: str = " -> ".join((*resolution_stack, resolved_source_name))
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' contains a cyclic helper CTE dependency while "
            f"inferring expected columns: {cycle_path}"
        )
    source_query: str | None = available_cte_queries_by_name.get(resolved_source_name)
    if source_query is None:
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' cannot infer columns from '{resolved_source_name}'; "
            "SELECT * is only supported for helper/mock CTEs authored in the same test file"
        )
    return _infer_query_column_names(
        query=source_query,
        file_path=file_path,
        available_cte_queries_by_name=available_cte_queries_by_name,
        resolution_stack=(*resolution_stack, resolved_source_name),
    )


def _resolve_star_source_name(
    *,
    source_name: str | None,
    statement: exp.Select,
    file_path: Path,
    source_name_by_alias: Mapping[str, str],
) -> str:
    if source_name is not None:
        resolved_source_name: str | None = source_name_by_alias.get(source_name)
        if resolved_source_name is None:
            raise SqlTestAssemblyError(
                f"SQL test '{file_path}' cannot resolve SELECT * source '{source_name}'"
            )
        return resolved_source_name
    if len(source_name_by_alias) != 1:
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' must use an explicit alias before SELECT * when "
            "the expected query reads from multiple sources"
        )
    return next(iter(source_name_by_alias.values()))


def _build_select_source_name_by_alias(statement: exp.Select) -> dict[str, str]:
    source_name_by_alias: dict[str, str] = {}
    from_expression: exp.From | None = cast(exp.From | None, statement.args.get("from_"))
    if from_expression is not None:
        _register_table_source(
            source_expression=from_expression.this, source_name_by_alias=source_name_by_alias
        )
    joins: tuple[exp.Expression, ...] = cast(
        tuple[exp.Expression, ...], tuple(statement.args.get("joins") or ())
    )
    join_expression: exp.Expression
    for join_expression in joins:
        if not isinstance(join_expression, exp.Join):
            continue
        _register_table_source(
            source_expression=join_expression.this, source_name_by_alias=source_name_by_alias
        )
    return source_name_by_alias


def _register_table_source(
    *,
    source_expression: exp.Expression | None,
    source_name_by_alias: dict[str, str],
) -> None:
    if not isinstance(source_expression, exp.Table):
        return
    source_name_by_alias[source_expression.alias_or_name] = source_expression.name


def _build_typed_expected_query(
    *,
    expected_query: str,
    expected_column_names: tuple[str, ...],
    output_column_type_by_name: Mapping[str, str],
) -> str:
    cast_projections: str = ",\n".join(
        f"    CAST({column_name} AS {output_column_type_by_name[column_name]}) AS {column_name}"
        for column_name in expected_column_names
    )
    return f"SELECT\n{cast_projections}\nFROM (\n{expected_query}\n) AS expected_source"
