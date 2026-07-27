"""Repair execution entrypoint."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError, AdapterResultError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
    AdapterStableBinding,
)
from streambuild.compiler.planner.main.build_deployment_physical_name import (
    build_deployment_physical_name,
)
from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult


def execute_repair_active_view(
    *,
    request: RepairActiveViewRequest,
    client: AdapterConnection,
) -> RepairActiveViewResult:
    """Explicitly rebind a stable active view to a chosen deployment table."""

    target_table_name: str = build_deployment_physical_name(
        logical_name=request.table_name, deployment_id=request.deployment_id
    )
    if not client.capabilities.stable_logical_bindings:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support stable logical bindings"
        )
    binding: AdapterStableBinding = AdapterStableBinding(
        database=request.default_database,
        logical_name=request.table_name,
        physical_name=target_table_name,
    )
    replacement_result: AdapterBindingReplacementResult = client.replace_stable_bindings(
        AdapterBindingReplacementRequest(bindings=(binding,))
    )
    if replacement_result.bindings != (binding,):
        raise AdapterResultError("Adapter returned a binding that did not match the repair request")
    return RepairActiveViewResult(
        table_name=request.table_name,
        target_table_name=target_table_name,
    )
