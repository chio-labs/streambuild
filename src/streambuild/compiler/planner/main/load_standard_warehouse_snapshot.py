"""Load one immutable standard-mode planning snapshot."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.compiler.planner.models import StandardWarehouseSnapshot


def load_standard_warehouse_snapshot(
    *, client: AdapterConnection, database: str
) -> StandardWarehouseSnapshot:
    """Read the catalog and durable ownership exactly once for standard planning."""

    if not client.capabilities.standard_rebuild:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support standard rebuilds"
        )
    return StandardWarehouseSnapshot(
        catalog=client.load_catalog(database),
        ownership_records=client.load_target_ownership(database),
    )
