"""Publish virtual workflow assembly outside executor internals."""

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.executor.backfill._helpers.workflow import (
    assemble_virtual_build_workflow as _assemble_virtual_build_workflow,
)
from sqltide.executor.backfill.models import BackfillBootstrapRequest
from sqltide.executor.workflow.models import BuildWorkflow


def assemble_virtual_build_workflow(
    *, request: BackfillBootstrapRequest, client: AdapterConnection, plan_json: str
) -> BuildWorkflow:
    """Return the authoritative virtual build workflow."""

    return _assemble_virtual_build_workflow(request=request, client=client, plan_json=plan_json)
