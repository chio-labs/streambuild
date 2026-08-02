"""Publish direct workflow assembly outside executor internals."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.direct._helpers.workflow import (
    assemble_direct_build_workflow as _assemble_direct_build_workflow,
)
from streambuild.executor.direct.models import DirectBuildRequest
from streambuild.executor.workflow.models import BuildWorkflow


def assemble_direct_build_workflow(
    *, request: DirectBuildRequest, client: AdapterConnection, plan_json: str
) -> BuildWorkflow:
    """Return the authoritative direct build workflow."""

    return _assemble_direct_build_workflow(request=request, client=client, plan_json=plan_json)
