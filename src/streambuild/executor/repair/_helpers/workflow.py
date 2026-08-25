"""Assemble exact repair workflow statements."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterBindingReplacementRequest, AdapterStableBinding
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_repair_workflow(
    *, binding: AdapterStableBinding, client: AdapterConnection
) -> tuple[WarehouseStatement, ...]:
    """Return the exact stable-view replacement statement."""

    rendered_sql: tuple[str, ...] = client.render_replace_stable_bindings(
        AdapterBindingReplacementRequest(bindings=(binding,))
    )
    return (
        WarehouseStatement(
            sequence=1,
            step_id="replace_active_view",
            phase=WorkflowPhase.FINALIZATION,
            intent=StatementIntent.MUTATION,
            sql=rendered_sql[0],
        ),
    )
