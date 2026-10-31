"""Load authoritative deployment inventory."""

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.executor.deployment._helpers.inventory import build_deployment_inventory
from sqltide.executor.deployment.models import DeploymentInventory


def load_deployments(
    *, client: AdapterConnection, metadata_database: str, default_database: str
) -> DeploymentInventory:
    """Return deterministic deployment inventory for one target database."""
    return build_deployment_inventory(
        client=client,
        metadata_database=metadata_database,
        default_database=default_database,
    )
