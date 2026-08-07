"""Persist terminal observations without changing command outcomes."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterInvocationRecord, AdapterNodeResultRecord
from streambuild.executor.observability._helpers.artifacts import publish_observation_artifact
from streambuild.executor.observability._helpers.workflow import assemble_observation_workflow
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main._execute_observation_workflow import (
    execute_observation_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement


def persist_terminal_observations(
    *,
    client: AdapterConnection,
    database: str,
    invocation: AdapterInvocationRecord,
    node_results: tuple[AdapterNodeResultRecord, ...],
) -> str | None:
    """Best-effort persistence that cannot alter the observed command outcome."""

    try:
        rendered: tuple[str, ...] = client.render_terminal_observations(
            database=database, invocation=invocation, node_results=node_results
        )
        statements: tuple[WarehouseStatement, ...] = assemble_observation_workflow(rendered)
        publish_observation_artifact(invocation=invocation, statements=statements)
        _ = execute_observation_workflow(statements=statements, connection=client)
    except (AdapterError, OSError, WorkflowExecutionError) as error:
        return f"Terminal observations were not recorded: {error}"
    return None
