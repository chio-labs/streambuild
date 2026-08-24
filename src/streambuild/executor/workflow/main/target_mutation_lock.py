"""Target-scoped mutation locking for warehouse operations."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterTargetMutationLock
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


@contextmanager
def target_mutation_lock(
    *, connection: AdapterConnection, database: str, ensure_database: bool = False
) -> Iterator[None]:
    """Hold exclusive target mutation ownership for one operation."""

    if ensure_database and not connection.database_exists(database):
        _ = execute_warehouse_workflow(
            statements=(
                WarehouseStatement(
                    sequence=1,
                    step_id="ensure_target_database_before_lock",
                    phase=WorkflowPhase.PREPARATION,
                    intent=StatementIntent.MUTATION,
                    sql=connection.render_ensure_database(database),
                ),
            ),
            connection=connection,
        )
    lock: AdapterTargetMutationLock = connection.acquire_target_mutation_lock(
        database=database,
        owner_id=str(uuid4()),
    )
    try:
        yield
    finally:
        connection.release_target_mutation_lock(lock)
