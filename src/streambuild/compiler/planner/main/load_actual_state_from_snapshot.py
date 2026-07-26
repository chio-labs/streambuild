"""Build actual state from one already-captured planning warehouse snapshot."""

from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner._helpers.actual_state import (
    build_inspected_actual_objects,
)
from streambuild.compiler.planner._helpers.actual_state_graph import build_actual_state
from streambuild.compiler.planner._helpers.warehouse_inspection import (
    load_actual_state_inspection,
)
from streambuild.compiler.planner.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualStateInspection,
    ActualTable,
    PlanningWarehouseSnapshot,
)


def load_actual_state_from_snapshot(
    *,
    snapshot: PlanningWarehouseSnapshot,
    desired_state: DesiredState,
    database: str,
) -> ActualState:
    """Build normalized actual state without performing another warehouse read."""

    inspection: ActualStateInspection = load_actual_state_inspection(
        snapshot=snapshot,
        desired_state=desired_state,
        database=database,
    )
    actual_objects: tuple[ActualKafkaTable | ActualTable | ActualMaterializedView, ...] = (
        build_inspected_actual_objects(
            desired_state=desired_state,
            inspection=inspection,
        )
    )
    return build_actual_state(actual_objects)
