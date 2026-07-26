"""Reconcile execution entrypoint."""

from __future__ import annotations

from datetime import UTC, datetime

from streambuild.compiler.actual_state.models import (
    ActualMaterializedView,
    ActualState,
    ActualTable,
)
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.metadata_state.models import ObjectStateRecord
from streambuild.compiler.shared.constants import TRANSFORM_TABLE_NAME_PREFIX
from streambuild.compiler.shared.models import DesiredMaterializedView, DesiredTable, ObjectKey
from streambuild.executor.reconcile._helpers.persist import (
    apply_reconcile,
    build_object_state_record,
)
from streambuild.executor.reconcile.constants import RECONCILE_DEPLOYMENT_ID_PREFIX
from streambuild.executor.reconcile.models import (
    ReconcilePreview,
    ReconcileRejectedTarget,
    ReconcileResult,
)
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def execute_reconcile(
    *,
    client: ClickHouseClient,
    metadata_database: str,
    desired_state: DesiredState,
    actual_state: ActualState,
    selected_model_keys: frozenset[ObjectKey],
    apply: bool = False,
) -> ReconcilePreview | ReconcileResult:
    """Preview or apply reconcile for structurally compatible live targets."""

    recorded_at: str = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    reconcile_id: str = (
        f"{RECONCILE_DEPLOYMENT_ID_PREFIX}{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    desired_table_by_key: dict[ObjectKey, DesiredTable] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
        and object_.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
    }
    desired_mv_by_target_key: dict[ObjectKey, DesiredMaterializedView] = {
        next(
            table.key
            for table in desired_table_by_key.values()
            if table.name == object_.target_table_name
        ): object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredMaterializedView)
        and object_.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
    }
    actual_table_by_key: dict[ObjectKey, ActualTable] = {
        object_.key: object_ for object_ in actual_state.objects if isinstance(object_, ActualTable)
    }
    actual_mv_by_key: dict[ObjectKey, ActualMaterializedView] = {
        object_.key: object_
        for object_ in actual_state.objects
        if isinstance(object_, ActualMaterializedView)
    }
    target_keys: tuple[ObjectKey, ...] = tuple(
        desired_table_by_key.keys()
        if not selected_model_keys
        else sorted(selected_model_keys, key=lambda key: key.name)
    )
    eligible_records: list[ObjectStateRecord] = []
    rejected_targets: list[ReconcileRejectedTarget] = []
    for target_key in target_keys:
        desired_table: DesiredTable | None = desired_table_by_key.get(target_key)
        if desired_table is None:
            continue
        desired_mv: DesiredMaterializedView | None = desired_mv_by_target_key.get(target_key)
        actual_table: ActualTable | None = actual_table_by_key.get(target_key)
        reasons: list[str] = []
        if actual_table is None:
            reasons.append("live target table not found")
        else:
            reasons.extend(
                _table_reconcile_rejection_reasons(
                    desired_table=desired_table, actual_table=actual_table
                )
            )
        if desired_mv is not None and desired_mv.key not in actual_mv_by_key:
            reasons.append("live transform materialized view not found")
        if reasons:
            rejected_targets.append(
                ReconcileRejectedTarget(
                    target_key=target_key,
                    target_name=desired_table.name,
                    reasons=tuple(reasons),
                )
            )
            continue
        eligible_records.append(
            build_object_state_record(
                desired_object=desired_table,
                reconcile_id=reconcile_id,
                recorded_at=recorded_at,
            )
        )
        if desired_mv is not None:
            eligible_records.append(
                build_object_state_record(
                    desired_object=desired_mv,
                    reconcile_id=reconcile_id,
                    recorded_at=recorded_at,
                )
            )
    preview: ReconcilePreview = ReconcilePreview(
        database=metadata_database,
        reconcile_id=reconcile_id,
        eligible_records=tuple(eligible_records),
        rejected_targets=tuple(rejected_targets),
    )
    if apply:
        return apply_reconcile(client=client, preview=preview)
    return preview


def _table_reconcile_rejection_reasons(
    *, desired_table: DesiredTable, actual_table: ActualTable
) -> list[str]:
    reasons: list[str] = []
    if desired_table.engine != actual_table.engine:
        reasons.append("engine does not match")
    if desired_table.order_by != actual_table.order_by:
        reasons.append("order_by does not match")
    if desired_table.partition_by != actual_table.partition_by:
        reasons.append("partition_by does not match")
    desired_columns: tuple[tuple[str, str], ...] = tuple(
        (column.name, column.type) for column in desired_table.columns
    )
    actual_columns: tuple[tuple[str, str], ...] = tuple(
        (column.name, column.type) for column in actual_table.columns
    )
    if desired_columns != actual_columns:
        reasons.append("columns or types do not match")
    return reasons
