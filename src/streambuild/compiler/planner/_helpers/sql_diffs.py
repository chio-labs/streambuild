"""SQL diff helpers for deployment planning."""

from __future__ import annotations

import difflib

from streambuild.clickhouse.render.main.render_create_kafka_table_ddl import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render.main.render_create_materialized_view_ddl import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render.main.render_create_table_ddl import render_create_table_ddl
from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualTable,
)
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.constants import (
    PLANNED_CHANGE_TYPE_CREATE,
    PLANNED_CHANGE_TYPE_NO_OP,
)
from streambuild.compiler.planner.models import PlannedObjectChange, PlannedSqlDiff
from streambuild.compiler.planner.types import PlannedChangeType
from streambuild.compiler.shared.constants import TRANSFORM_TABLE_NAME_PREFIX
from streambuild.compiler.shared.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    ObjectKey,
)


def build_planned_sql_diffs(
    *,
    desired_state: DesiredState,
    actual_state: ActualState,
    object_changes: tuple[PlannedObjectChange, ...],
    default_database: str,
) -> tuple[PlannedSqlDiff, ...]:
    """Build unified SQL diffs for changed desired objects."""

    desired_by_key: dict[
        ObjectKey,
        DesiredKafkaTable | DesiredTable | DesiredMaterializedView,
    ] = {object_.key: object_ for object_ in desired_state.objects}
    actual_by_key: dict[ObjectKey, ActualKafkaTable | ActualTable | ActualMaterializedView] = {
        object_.key: object_ for object_ in actual_state.objects
    }
    sql_diffs: list[PlannedSqlDiff] = []
    object_change: PlannedObjectChange
    for object_change in object_changes:
        if object_change.change_type == PLANNED_CHANGE_TYPE_NO_OP:
            continue
        desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | None = (
            desired_by_key.get(object_change.key)
        )
        if desired_object is None:
            continue
        desired_sql: str = _render_desired_object_sql(
            object_=desired_object,
            default_database=default_database,
        )
        actual_object: ActualKafkaTable | ActualTable | ActualMaterializedView | None = (
            actual_by_key.get(object_change.key)
        )
        current_change_type: PlannedChangeType = PlannedChangeType(object_change.change_type)
        current_sql: str = (
            ""
            if current_change_type == PLANNED_CHANGE_TYPE_CREATE or actual_object is None
            else _render_actual_object_sql(
                object_=actual_object,
                default_database=default_database,
            )
        )
        sql_diffs.append(
            PlannedSqlDiff(
                key=object_change.key,
                object_type=_display_object_type(desired_object),
                name=desired_object.name,
                diff_lines=_build_unified_diff_lines(
                    current_sql=current_sql, desired_sql=desired_sql
                ),
            )
        )
    return tuple(sql_diffs)


def _render_desired_object_sql(
    *,
    object_: DesiredKafkaTable | DesiredTable | DesiredMaterializedView,
    default_database: str,
) -> str:
    database: str = object_.key.database or default_database
    if isinstance(object_, DesiredKafkaTable):
        return render_create_kafka_table_ddl(table=object_, database=database)
    if isinstance(object_, DesiredTable):
        return render_create_table_ddl(table=object_, database=database)
    return render_create_materialized_view_ddl(materialized_view=object_, database=database)


def _render_actual_object_sql(
    *,
    object_: ActualKafkaTable | ActualTable | ActualMaterializedView,
    default_database: str,
) -> str:
    database: str = object_.key.database or default_database
    if isinstance(object_, ActualKafkaTable):
        return render_create_kafka_table_ddl(
            table=DesiredKafkaTable(key=object_.key, deps=(), spec=object_.spec),
            database=database,
        )
    if isinstance(object_, ActualTable):
        return render_create_table_ddl(
            table=DesiredTable(key=object_.key, deps=(), spec=object_.spec),
            database=database,
        )
    return render_create_materialized_view_ddl(
        materialized_view=DesiredMaterializedView(key=object_.key, deps=(), spec=object_.spec),
        database=database,
    )


def _display_object_type(
    object_: DesiredKafkaTable | DesiredTable | DesiredMaterializedView,
) -> str:
    if isinstance(object_, DesiredMaterializedView) and object_.target_table_name.startswith(
        TRANSFORM_TABLE_NAME_PREFIX
    ):
        return "transform"
    if isinstance(object_, DesiredKafkaTable):
        return "kafka table"
    if isinstance(object_, DesiredTable):
        return "table"
    return "materialized view"


def _build_unified_diff_lines(*, current_sql: str, desired_sql: str) -> tuple[str, ...]:
    return tuple(
        difflib.unified_diff(
            current_sql.splitlines(),
            desired_sql.splitlines(),
            fromfile="current",
            tofile="desired",
            lineterm="",
        )
    )
