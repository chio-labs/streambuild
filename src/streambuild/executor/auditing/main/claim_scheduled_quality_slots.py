"""Elect one scheduler process for each due logical slot."""

from time import sleep

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterQualityScheduleClaim
from streambuild.executor.auditing._helpers.schedule_claim_workflow import (
    assemble_schedule_claim_workflow,
)
from streambuild.executor.auditing.constants import SCHEDULE_CLAIM_ELECTION_WINDOW_SECONDS
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement


def claim_scheduled_quality_slots(
    *,
    connection: AdapterConnection,
    database: str,
    project_identity: str,
    target_identity: str,
    owner_id: str,
    claims: tuple[AdapterQualityScheduleClaim, ...],
) -> frozenset[AdapterQualityScheduleClaim] | None:
    """Persist contenders, then return slots won by the earliest warehouse claims."""

    rendered: tuple[str, ...] = connection.render_scheduled_quality_slot_claims(
        database=database,
        project_identity=project_identity,
        target_identity=target_identity,
        owner_id=owner_id,
        claims=claims,
    )
    if not rendered:
        return None
    statements: tuple[WarehouseStatement, ...] = assemble_schedule_claim_workflow(rendered)
    _ = execute_warehouse_workflow(statements=statements, connection=connection)
    sleep(SCHEDULE_CLAIM_ELECTION_WINDOW_SECONDS)
    return connection.load_scheduled_quality_slot_claim_winners(
        database=database,
        project_identity=project_identity,
        target_identity=target_identity,
        owner_id=owner_id,
        claims=claims,
    )
