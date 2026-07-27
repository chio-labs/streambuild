"""Capture all non-dynamic warehouse reads needed by one planning invocation."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import CatalogSnapshot
from streambuild.compiler.planner._helpers.warehouse_metadata import (
    load_all_object_state_records,
)
from streambuild.compiler.planner.models import ObjectStateRecord, PlanningWarehouseSnapshot


def load_planning_warehouse_snapshot(
    *,
    client: AdapterConnection,
    database: str,
) -> PlanningWarehouseSnapshot:
    """Load one immutable catalog and metadata snapshot after capability validation."""

    if not client.capabilities.virtual_environments:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support virtual environments"
        )
    catalog: CatalogSnapshot = client.load_catalog(database)
    object_state_records: tuple[ObjectStateRecord, ...] = load_all_object_state_records(
        client=client,
        metadata_database=database,
    )
    return PlanningWarehouseSnapshot(
        catalog=catalog,
        object_state_records=object_state_records,
    )
