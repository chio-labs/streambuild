"""Load actual warehouse state for the managed objects of a pipeline."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.actual_state._helpers.assembly import (
    build_inspected_actual_objects,
)
from streambuild.compiler.actual_state._helpers.inspection import (
    load_actual_state_inspection,
)
from streambuild.compiler.actual_state.main._build_actual_state import build_actual_state
from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualStateInspection,
    ActualTable,
)
from streambuild.compiler.compile.models import DesiredState


def load_actual_state(
    *,
    client: AdapterConnection,
    desired_state: DesiredState,
    database: str,
) -> ActualState:
    """Load the current active actual state from ClickHouse inspection."""

    inspection: ActualStateInspection = load_actual_state_inspection(
        client=client,
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
