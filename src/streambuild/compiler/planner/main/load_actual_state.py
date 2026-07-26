"""Load actual warehouse state for the managed objects of a pipeline."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.main.load_actual_state_from_snapshot import (
    load_actual_state_from_snapshot,
)
from streambuild.compiler.planner.main.load_planning_warehouse_snapshot import (
    load_planning_warehouse_snapshot,
)
from streambuild.compiler.planner.models import ActualState, PlanningWarehouseSnapshot


def load_actual_state(
    *,
    client: AdapterConnection,
    desired_state: DesiredState,
    database: str,
) -> ActualState:
    """Load the current active actual state from ClickHouse inspection."""

    snapshot: PlanningWarehouseSnapshot = load_planning_warehouse_snapshot(
        client=client,
        database=database,
    )
    return load_actual_state_from_snapshot(
        snapshot=snapshot,
        desired_state=desired_state,
        database=database,
    )
