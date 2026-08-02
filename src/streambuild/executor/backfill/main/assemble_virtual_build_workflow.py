"""Publish virtual workflow assembly outside executor internals."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.backfill._helpers.workflow import (
    assemble_virtual_build_workflow as _assemble_virtual_build_workflow,
)
from streambuild.executor.backfill.models import BackfillBootstrapRequest
from streambuild.executor.workflow.models import BuildWorkflow


def assemble_virtual_build_workflow(
    *, request: BackfillBootstrapRequest, client: AdapterConnection, plan_json: str
) -> BuildWorkflow:
    """Return the authoritative virtual build workflow."""

    return _assemble_virtual_build_workflow(request=request, client=client, plan_json=plan_json)
