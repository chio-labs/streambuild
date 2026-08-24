"""Publish destruction workflow assembly."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.destruction._helpers.workflow import (
    assemble_destruction_workflow as _assemble_destruction_workflow,
)
from streambuild.executor.destruction.models import DestructionPlan
from streambuild.executor.workflow.models import WarehouseStatement


def assemble_destruction_workflow(
    *,
    plan: DestructionPlan,
    connection: AdapterConnection | None = None,
) -> tuple[WarehouseStatement, ...]:
    """Drop frozen owned relations in stable reverse-dependency order."""

    return _assemble_destruction_workflow(plan=plan, connection=connection)
