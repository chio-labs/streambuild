"""Assemble sensor state persistence statements."""

from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_sensor_state_workflow(rendered: tuple[str, ...]) -> tuple[WarehouseStatement, ...]:
    """Wrap exact adapter SQL for the sole warehouse mutation gateway."""

    return tuple(
        WarehouseStatement(
            sequence=index,
            step_id=f"record_sensor_state_{index}",
            phase=WorkflowPhase.FINALIZATION,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for index, sql in enumerate(rendered, start=1)
    )
