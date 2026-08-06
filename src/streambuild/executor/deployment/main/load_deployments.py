"""Load authoritative deployment inventory."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.deployment._helpers.inventory import build_deployment_inventory
from streambuild.executor.deployment.models import DeploymentInventory


def load_deployments(
    *, client: AdapterConnection, metadata_database: str, default_database: str
) -> DeploymentInventory:
    """Return deterministic deployment inventory for one target database."""
    return build_deployment_inventory(
        client=client,
        metadata_database=metadata_database,
        default_database=default_database,
    )
