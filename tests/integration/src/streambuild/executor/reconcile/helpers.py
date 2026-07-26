from streambuild.compiler.actual_state.models import (
    ActualMaterializedView,
    ActualState,
    ActualTable,
)
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


def build_matching_reconcile_states() -> tuple[DesiredState, ActualState]:
    target_key: ObjectKey = ObjectKey(None, "table", "tbl__orders")
    desired_table: DesiredTable = DesiredTable(
        key=target_key,
        deps=(),
        spec=TableSpec(
            columns=(Column(name="order_id", type="String"),),
            storage=TableStorage(engine="MergeTree()", order_by=("order_id",)),
        ),
    )
    desired_view: DesiredMaterializedView = DesiredMaterializedView(
        key=ObjectKey(None, "materialized_view", "mv__orders"),
        deps=(target_key,),
        spec=MaterializedViewSpec(
            source_table_name="raw__orders",
            target_table_name="tbl__orders",
            query="SELECT order_id FROM raw__orders",
        ),
    )
    desired_state: DesiredState = DesiredState(
        objects=(desired_table, desired_view),
        replay_anchor_keys=frozenset(),
        mutable_ref_warning_keys=frozenset(),
    )
    actual_state: ActualState = ActualState(
        objects=(
            ActualTable(key=desired_table.key, spec=desired_table.spec),
            ActualMaterializedView(key=desired_view.key, spec=desired_view.spec),
        )
    )
    return desired_state, actual_state
