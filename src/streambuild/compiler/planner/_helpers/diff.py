"""Desired-vs-actual diff helpers for planning."""

from __future__ import annotations

from sqlglot import exp, parse_one

from streambuild.compiler.actual_state.models import ActualState, ActualTable
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.constants import (
    ADD_ONLY_COLUMN_DIFFERENCE,
    PLANNED_CHANGE_TYPE_CREATE,
    PLANNED_CHANGE_TYPE_NO_OP,
    PLANNED_CHANGE_TYPE_REBUILD,
    TABLE_SCHEMA_CHANGE_KIND_BREAKING,
    TABLE_SCHEMA_CHANGE_KIND_NON_BREAKING,
    TABLE_SCHEMA_SEED_COMPATIBILITY_NON_SEEDABLE,
    TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE,
    TYPE_CHANGE_COLUMN_DIFFERENCE,
)
from streambuild.compiler.planner.exceptions import DeploymentPlanError
from streambuild.compiler.planner.models import PlannedObjectChange
from streambuild.compiler.planner.types import (
    ActualObject,
    DesiredObject,
    PlannedChangeType,
    TableSchemaChangeKind,
    TableSchemaSeedCompatibility,
)
from streambuild.compiler.shared.models import Column, DesiredTable, ObjectKey, TableSpec


def classify_object_changes(
    *,
    desired_state: DesiredState,
    actual_state: ActualState,
    full_refresh_keys: frozenset[ObjectKey] = frozenset(),
    start_time_keys: frozenset[ObjectKey] = frozenset(),
    start_time: str | None = None,
) -> tuple[PlannedObjectChange, ...]:
    """Classify conservative desired-vs-actual object changes."""

    actual_by_key: dict[ObjectKey, ActualObject] = {
        object_.key: object_ for object_ in actual_state.objects
    }
    planned_changes: list[PlannedObjectChange] = []
    desired_object: DesiredObject
    for desired_object in desired_state.objects:
        actual_object: ActualObject | None = actual_by_key.get(desired_object.key)
        force_full_refresh: bool = desired_object.key in full_refresh_keys
        forced_start_time: str | None = (
            start_time if desired_object.key in start_time_keys else None
        )
        if actual_object is None:
            planned_changes.append(
                PlannedObjectChange(
                    key=desired_object.key,
                    change_type=PLANNED_CHANGE_TYPE_CREATE,
                    force_full_refresh=force_full_refresh,
                    forced_start_time=forced_start_time,
                )
            )
            continue

        change_type: PlannedChangeType = classify_object_change_type(
            desired_object=desired_object,
            actual_object=actual_object,
            force_full_refresh=force_full_refresh,
            forced_start_time=forced_start_time,
        )
        schema_change_kind: TableSchemaChangeKind | None = classify_table_schema_change_kind(
            desired_object=desired_object, actual_object=actual_object
        )
        seed_compatibility: TableSchemaSeedCompatibility | None = classify_table_seed_compatibility(
            desired_object=desired_object, actual_object=actual_object
        )
        planned_changes.append(
            PlannedObjectChange(
                key=desired_object.key,
                change_type=change_type,
                force_full_refresh=force_full_refresh,
                forced_start_time=forced_start_time,
                schema_change_kind=schema_change_kind,
                seed_compatibility=seed_compatibility,
            )
        )

    return tuple(planned_changes)


def classify_object_change_type(
    *,
    desired_object: DesiredObject,
    actual_object: ActualObject,
    force_full_refresh: bool = False,
    forced_start_time: str | None = None,
) -> PlannedChangeType:
    """Classify a single desired-vs-actual object comparison."""

    if force_full_refresh:
        return PLANNED_CHANGE_TYPE_REBUILD
    if forced_start_time is not None:
        return PLANNED_CHANGE_TYPE_REBUILD
    if _specs_equal(desired_object=desired_object, actual_object=actual_object):
        return PLANNED_CHANGE_TYPE_NO_OP
    return PLANNED_CHANGE_TYPE_REBUILD


def classify_table_schema_change_kind(
    *, desired_object: DesiredObject, actual_object: ActualObject
) -> TableSchemaChangeKind | None:
    """Classify table-column compatibility for planner policy decisions."""

    if not isinstance(desired_object, DesiredTable) or not isinstance(actual_object, ActualTable):
        return None
    column_difference: str | None = _classify_table_column_difference(
        desired_columns=desired_object.columns,
        actual_columns=actual_object.columns,
    )
    if column_difference is None:
        return None
    if column_difference == ADD_ONLY_COLUMN_DIFFERENCE:
        return TABLE_SCHEMA_CHANGE_KIND_NON_BREAKING
    return TABLE_SCHEMA_CHANGE_KIND_BREAKING


def classify_table_seed_compatibility(
    *, desired_object: DesiredObject, actual_object: ActualObject
) -> TableSchemaSeedCompatibility | None:
    """Classify whether table schema changes can safely seed from active data."""

    if not isinstance(desired_object, DesiredTable) or not isinstance(actual_object, ActualTable):
        return None
    column_difference: str | None = _classify_table_column_difference(
        desired_columns=desired_object.columns,
        actual_columns=actual_object.columns,
    )
    if column_difference is None:
        return None
    if column_difference == TYPE_CHANGE_COLUMN_DIFFERENCE:
        return TABLE_SCHEMA_SEED_COMPATIBILITY_NON_SEEDABLE
    return TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE


def _classify_table_column_difference(
    *, desired_columns: tuple[Column, ...], actual_columns: tuple[Column, ...]
) -> str | None:
    desired_columns_by_name: dict[str, Column] = {column.name: column for column in desired_columns}
    actual_columns_by_name: dict[str, Column] = {column.name: column for column in actual_columns}
    added_column_names: set[str] = set(desired_columns_by_name) - set(actual_columns_by_name)
    removed_column_names: set[str] = set(actual_columns_by_name) - set(desired_columns_by_name)
    changed_columns: set[str] = {
        column_name
        for column_name in set(desired_columns_by_name) & set(actual_columns_by_name)
        if not _columns_equal(
            desired_column=desired_columns_by_name[column_name],
            actual_column=actual_columns_by_name[column_name],
        )
    }
    if not added_column_names and not removed_column_names and not changed_columns:
        return None
    if changed_columns:
        return "type_change"
    if added_column_names and not removed_column_names:
        return "add_only"
    if removed_column_names and not added_column_names:
        return "remove_only"
    return "add_and_remove"


def _specs_equal(*, desired_object: DesiredObject, actual_object: ActualObject) -> bool:
    if isinstance(desired_object, DesiredTable) and isinstance(actual_object, ActualTable):
        return _table_specs_equal(desired_spec=desired_object.spec, actual_spec=actual_object.spec)
    return desired_object.spec == actual_object.spec


def _table_specs_equal(*, desired_spec: TableSpec, actual_spec: TableSpec) -> bool:
    return (
        _columns_equal_tuple(
            desired_columns=desired_spec.columns, actual_columns=actual_spec.columns
        )
        and desired_spec.storage == actual_spec.storage
    )


def _columns_equal_tuple(
    *, desired_columns: tuple[Column, ...], actual_columns: tuple[Column, ...]
) -> bool:
    if len(desired_columns) != len(actual_columns):
        return False
    return all(
        _columns_equal(desired_column=desired_column, actual_column=actual_column)
        for desired_column, actual_column in zip(desired_columns, actual_columns, strict=True)
    )


def _columns_equal(*, desired_column: Column, actual_column: Column) -> bool:
    return (
        desired_column.name == actual_column.name
        and _normalize_clickhouse_type(desired_column.type)
        == _normalize_clickhouse_type(actual_column.type)
        and desired_column.default == actual_column.default
    )


def _normalize_clickhouse_type(type_sql: str) -> str:
    parsed_expression: exp.Expr = parse_one(
        f"CREATE TABLE t (c {type_sql}) ENGINE = MergeTree ORDER BY tuple()",
        dialect="clickhouse",
    )
    if not isinstance(parsed_expression, exp.Create):
        raise DeploymentPlanError(f"Expected CREATE statement when normalizing type '{type_sql}'")
    column_definition: exp.ColumnDef = next(parsed_expression.find_all(exp.ColumnDef))
    data_type: exp.DataType | None = column_definition.kind
    if data_type is None:
        raise DeploymentPlanError(f"Expected column type when normalizing type '{type_sql}'")
    return data_type.sql(dialect="clickhouse")
