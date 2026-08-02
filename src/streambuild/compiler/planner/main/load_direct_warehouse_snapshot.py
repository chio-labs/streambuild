"""Load one immutable direct-mode planning snapshot."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.compiler.planner.models import DirectWarehouseSnapshot


def load_direct_warehouse_snapshot(
    *, client: AdapterConnection, database: str, metadata_database: str
) -> DirectWarehouseSnapshot:
    """Read the catalog and durable ownership exactly once for direct planning."""

    if not client.capabilities.direct_rebuild:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support direct rebuilds"
        )
    return DirectWarehouseSnapshot(
        catalog=client.load_catalog(database),
        ownership_records=client.load_target_ownership(metadata_database),
        deployment_inventory=client.load_deployment_inventory(metadata_database),
    )
