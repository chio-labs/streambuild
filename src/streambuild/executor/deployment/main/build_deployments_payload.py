"""Entry returning every deployment as a serializable inventory payload."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.deployment._helpers.payload import build_inventory_payload


def build_deployments_payload(
    *, connection: AdapterConnection, database: str, metadata_database: str
) -> dict[str, object]:
    """Return every reconstructed deployment with storage totals."""

    return build_inventory_payload(
        connection=connection,
        database=database,
        metadata_database=metadata_database,
    )
