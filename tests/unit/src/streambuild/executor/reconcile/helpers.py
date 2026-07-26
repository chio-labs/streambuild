from streambuild.compiler.compile.models import (
    Column,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.planner.models import (
    ActualMaterializedView,
    ActualState,
    ActualTable,
)


def build_matching_reconcile_states() -> tuple[DesiredState, ActualState]:
    desired_table: DesiredTable = _build_desired_table()
    desired_view: DesiredMaterializedView = _build_desired_view(desired_table.key)
    desired_state: DesiredState = _build_desired_state(desired_table, desired_view)
    actual_state: ActualState = ActualState(
        objects=(
            ActualTable(key=desired_table.key, spec=desired_table.spec),
            ActualMaterializedView(key=desired_view.key, spec=desired_view.spec),
        )
    )
    return desired_state, actual_state


def build_structurally_mismatched_reconcile_states() -> tuple[DesiredState, ActualState]:
    desired_table: DesiredTable = _build_desired_table()
    desired_view: DesiredMaterializedView = _build_desired_view(desired_table.key)
    desired_state: DesiredState = _build_desired_state(desired_table, desired_view)
    actual_state: ActualState = ActualState(
        objects=(
            ActualTable(
                key=desired_table.key,
                spec=TableSpec(
                    columns=desired_table.columns,
                    storage=TableStorage(
                        engine="ReplacingMergeTree()",
                        order_by=desired_table.order_by,
                    ),
                ),
            ),
        )
    )
    return desired_state, actual_state


def _build_desired_table() -> DesiredTable:
    target_key: ObjectKey = ObjectKey(
        database=None,
        object_type="table",
        name="tbl__orders",
    )
    return DesiredTable(
        key=target_key,
        deps=(),
        spec=TableSpec(
            columns=(Column(name="order_id", type="String"),),
            storage=TableStorage(
                engine="MergeTree()",
                order_by=("order_id",),
            ),
        ),
    )


def _build_desired_view(target_key: ObjectKey) -> DesiredMaterializedView:
    return DesiredMaterializedView(
        key=ObjectKey(
            database=None,
            object_type="materialized_view",
            name="mv__orders",
        ),
        deps=(target_key,),
        spec=MaterializedViewSpec(
            source_table_name="raw__orders",
            target_table_name=target_key.name,
            query="SELECT order_id FROM raw__orders",
        ),
    )


def _build_desired_state(
    desired_table: DesiredTable,
    desired_view: DesiredMaterializedView,
) -> DesiredState:
    return DesiredState(
        objects=(desired_table, desired_view),
        replay_anchor_keys=frozenset(),
        mutable_ref_warning_keys=frozenset(),
    )
