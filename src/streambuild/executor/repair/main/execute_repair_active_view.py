"""Repair execution entrypoint."""

from uuid import uuid4

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import OWNERSHIP_EVENT_OWNED
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import (
    AdapterOwnedResourceEvent,
    AdapterOwnedResourceSnapshot,
    AdapterStableBinding,
)
from streambuild.adapter.types import AdapterOptionalStateStatus
from streambuild.compiler.planner.main.build_deployment_physical_name import (
    build_deployment_physical_name,
)
from streambuild.executor.repair._helpers.workflow import assemble_repair_workflow
from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.main.target_mutation_lock import target_mutation_lock
from streambuild.executor.workflow.models import WarehouseStatement


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
    with target_mutation_lock(connection=client, database=request.default_database):
        binding: AdapterStableBinding = AdapterStableBinding(
            database=request.default_database,
            logical_name=request.table_name,
            physical_name=target_table_name,
        )
        snapshot: AdapterOwnedResourceSnapshot = client.load_owned_resources(
            database=request.default_database,
            target_database=request.default_database,
        )
        if snapshot.status == AdapterOptionalStateStatus.UNAVAILABLE:
            raise AdapterCapabilityError(snapshot.warning or "Owned-resource ledger is unavailable")
        by_name: dict[str, AdapterOwnedResourceEvent] = {
            event.resource_name: event for event in snapshot.resources
        }
        authority: AdapterOwnedResourceEvent | None = by_name.get(
            request.table_name
        ) or by_name.get(target_table_name)
        ownership_event: AdapterOwnedResourceEvent = AdapterOwnedResourceEvent(
            event_id=f"owned_{uuid4().hex}",
            event_type=OWNERSHIP_EVENT_OWNED,
            target_database=request.default_database,
            resource_database=request.default_database,
            resource_name=request.table_name,
            resource_kind="view",
            pipeline_name="" if authority is None else authority.pipeline_name,
            logical_resource_type="model",
            logical_resource_name=(
                request.table_name if authority is None else authority.logical_resource_name
            ),
            resource_role="stable_binding",
        )
        statements: tuple[WarehouseStatement, ...] = assemble_repair_workflow(
            binding=binding,
            ownership_event=ownership_event,
            metadata_database=request.default_database,
            client=client,
        )
        _ = execute_warehouse_workflow(statements=statements, connection=client)
        return RepairActiveViewResult(
            table_name=request.table_name,
            target_table_name=target_table_name,
        )
