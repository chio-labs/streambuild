"""Assemble scheduled quality-slot claim mutations."""

from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_schedule_claim_workflow(rendered: tuple[str, ...]) -> tuple[WarehouseStatement, ...]:
    """Wrap exact adapter SQL for the sole warehouse mutation gateway."""

    return tuple(
        WarehouseStatement(
            sequence=index,
            step_id=f"claim_scheduled_quality_slot_{index}",
            phase=WorkflowPhase.PREFLIGHT,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for index, sql in enumerate(rendered, start=1)
    )
