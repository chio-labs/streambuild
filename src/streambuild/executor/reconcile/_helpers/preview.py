"""Build reconcile previews from desired and actual object state."""

from datetime import UTC, datetime

from streambuild.compiler.compile.constants import TRANSFORM_TABLE_NAME_PREFIX
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ObjectKey,
)
from streambuild.compiler.metadata_state.models import ObjectStateRecord
from streambuild.compiler.planner.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualTable,
)
from streambuild.executor.reconcile._helpers.persist import build_object_state_record
from streambuild.executor.reconcile.constants import RECONCILE_DEPLOYMENT_ID_PREFIX
from streambuild.executor.reconcile.models import (
    ReconcileObjectIndex,
    ReconcilePreview,
    ReconcileRejectedTarget,
)


def build_reconcile_preview(
    *,
    metadata_database: str,
    desired_state: DesiredState,
    actual_state: ActualState,
    selected_model_keys: frozenset[ObjectKey],
) -> ReconcilePreview:
    """Build reconcile eligibility records and target rejections."""

    recorded_at: str = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    reconcile_id: str = (
        f"{RECONCILE_DEPLOYMENT_ID_PREFIX}{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    object_index: ReconcileObjectIndex = _build_reconcile_object_index(
        desired_state=desired_state,
        actual_state=actual_state,
        selected_model_keys=selected_model_keys,
    )
    eligible_records: list[ObjectStateRecord] = []
    rejected_targets: list[ReconcileRejectedTarget] = []
    target_key: ObjectKey
    for target_key in object_index.target_keys:
        target_records: tuple[ObjectStateRecord, ...]
        rejected_target: ReconcileRejectedTarget | None
        target_records, rejected_target = _classify_reconcile_target(
            target_key=target_key,
            object_index=object_index,
            reconcile_id=reconcile_id,
            recorded_at=recorded_at,
        )
        eligible_records.extend(target_records)
        if rejected_target is not None:
            rejected_targets.append(rejected_target)
    return ReconcilePreview(
        database=metadata_database,
        reconcile_id=reconcile_id,
        eligible_records=tuple(eligible_records),
        rejected_targets=tuple(rejected_targets),
    )


def _build_reconcile_object_index(
    *,
    desired_state: DesiredState,
    actual_state: ActualState,
    selected_model_keys: frozenset[ObjectKey],
) -> ReconcileObjectIndex:
    desired_table_by_key: dict[ObjectKey, DesiredTable] = {}
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        if isinstance(desired_object, DesiredTable) and desired_object.name.startswith(
            TRANSFORM_TABLE_NAME_PREFIX
        ):
            desired_table_by_key[desired_object.key] = desired_object

    desired_mv_by_target_key: dict[ObjectKey, DesiredMaterializedView] = {}
    for desired_object in desired_state.objects:
        if not isinstance(desired_object, DesiredMaterializedView):
            continue
        if not desired_object.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
            continue
        target_key: ObjectKey = next(
            table.key
            for table in desired_table_by_key.values()
            if table.name == desired_object.target_table_name
        )
        desired_mv_by_target_key[target_key] = desired_object

    actual_table_by_key: dict[ObjectKey, ActualTable] = {}
    actual_mv_by_key: dict[ObjectKey, ActualMaterializedView] = {}
    actual_object: ActualKafkaTable | ActualTable | ActualMaterializedView
    for actual_object in actual_state.objects:
        if isinstance(actual_object, ActualTable):
            actual_table_by_key[actual_object.key] = actual_object
        elif isinstance(actual_object, ActualMaterializedView):
            actual_mv_by_key[actual_object.key] = actual_object

    target_keys: tuple[ObjectKey, ...] = tuple(
        desired_table_by_key.keys()
        if not selected_model_keys
        else sorted(selected_model_keys, key=lambda key: key.name)
    )
    return ReconcileObjectIndex(
        desired_table_by_key=desired_table_by_key,
        desired_mv_by_target_key=desired_mv_by_target_key,
        actual_table_by_key=actual_table_by_key,
        actual_mv_by_key=actual_mv_by_key,
        target_keys=target_keys,
    )


def _classify_reconcile_target(
    *,
    target_key: ObjectKey,
    object_index: ReconcileObjectIndex,
    reconcile_id: str,
    recorded_at: str,
) -> tuple[tuple[ObjectStateRecord, ...], ReconcileRejectedTarget | None]:
    desired_table: DesiredTable | None = object_index.desired_table_by_key.get(target_key)
    if desired_table is None:
        return (), None
    desired_mv: DesiredMaterializedView | None = object_index.desired_mv_by_target_key.get(
        target_key
    )
    actual_table: ActualTable | None = object_index.actual_table_by_key.get(target_key)
    reasons: list[str] = []
    if actual_table is None:
        reasons.append("live target table not found")
    else:
        reasons.extend(
            _table_reconcile_rejection_reasons(
                desired_table=desired_table,
                actual_table=actual_table,
            )
        )
    if desired_mv is not None and desired_mv.key not in object_index.actual_mv_by_key:
        reasons.append("live transform materialized view not found")
    if reasons:
        return (), ReconcileRejectedTarget(
            target_key=target_key,
            target_name=desired_table.name,
            reasons=tuple(reasons),
        )

    eligible_records: list[ObjectStateRecord] = [
        build_object_state_record(
            desired_object=desired_table,
            reconcile_id=reconcile_id,
            recorded_at=recorded_at,
        )
    ]
    if desired_mv is not None:
        eligible_records.append(
            build_object_state_record(
                desired_object=desired_mv,
                reconcile_id=reconcile_id,
                recorded_at=recorded_at,
            )
        )
    return tuple(eligible_records), None


def _table_reconcile_rejection_reasons(
    *,
    desired_table: DesiredTable,
    actual_table: ActualTable,
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
