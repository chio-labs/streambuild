"""Persist a complete project manifest before warehouse execution."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterManifest
from streambuild.executor.observability._helpers.workflow import assemble_observation_workflow
from streambuild.executor.workflow.main._execute_observation_workflow import (
    execute_observation_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement


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
