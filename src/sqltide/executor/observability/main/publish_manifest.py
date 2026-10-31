"""Persist a complete project manifest before warehouse execution."""

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.adapter.models import AdapterManifest
from sqltide.executor.observability._helpers.workflow import assemble_observation_workflow
from sqltide.executor.workflow.main._execute_observation_workflow import (
    execute_observation_workflow,
)
from sqltide.executor.workflow.models import WarehouseStatement


def publish_manifest(
    *, connection: AdapterConnection, database: str, manifest: AdapterManifest
) -> None:
    """Append one manifest through the warehouse mutation gateway."""

    if not database:
        return
    rendered: tuple[str, ...] = connection.render_manifest_publication(
        database=database, manifest=manifest
    )
    statements: tuple[WarehouseStatement, ...] = assemble_observation_workflow(rendered)
    _ = execute_observation_workflow(statements=statements, connection=connection)
