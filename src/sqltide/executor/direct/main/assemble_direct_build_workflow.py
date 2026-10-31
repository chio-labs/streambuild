"""Publish direct workflow assembly outside executor internals."""

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.compiler.planner.models import DirectWarehouseSnapshot
from sqltide.executor.direct._helpers.workflow import (
    assemble_direct_build_workflow as _assemble_direct_build_workflow,
)
from sqltide.executor.direct.models import DirectBuildRequest, DirectBuildWorkflow


def assemble_direct_build_workflow(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    snapshot: DirectWarehouseSnapshot,
    plan_json: str,
) -> DirectBuildWorkflow:
    """Return the authoritative direct build workflow."""

    return _assemble_direct_build_workflow(
        request=request,
        client=client,
        snapshot=snapshot,
        plan_json=plan_json,
    )
