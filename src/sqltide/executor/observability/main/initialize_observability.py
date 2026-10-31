"""Initialize the current observability schema before warehouse planning."""

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.executor.observability._helpers.workflow import assemble_observation_workflow
from sqltide.executor.workflow.main._execute_observation_workflow import (
    execute_observation_workflow,
)
from sqltide.executor.workflow.models import WarehouseStatement


def initialize_observability(*, connection: AdapterConnection, database: str) -> None:
    """Require the current observability schema before warehouse planning."""

    if not database:
        return
    rendered: tuple[str, ...] = connection.render_migrate_metadata_state(database)
    statements: tuple[WarehouseStatement, ...] = assemble_observation_workflow(rendered)
    _ = execute_observation_workflow(statements=statements, connection=connection)
