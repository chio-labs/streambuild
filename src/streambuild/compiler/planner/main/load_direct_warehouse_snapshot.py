"""Load one immutable direct-mode planning snapshot."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.compiler.planner.models import DirectWarehouseSnapshot


def load_direct_warehouse_snapshot(
    *,
    client: AdapterConnection,
    database: str,
    metadata_database: str | None = None,
    logical_model_identities: tuple[str, ...] = (),
) -> DirectWarehouseSnapshot:
    """Read the target catalog required for Direct planning."""

    if not client.capabilities.direct_rebuild:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support direct rebuilds"
        )
    return DirectWarehouseSnapshot(
        catalog=client.load_catalog(database),
        fingerprints=client.load_direct_fingerprints(
            database=metadata_database or database,
            logical_model_identities=logical_model_identities,
        ),
    )
