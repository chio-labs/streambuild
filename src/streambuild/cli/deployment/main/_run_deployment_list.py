"""List virtual deployments."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.deployment._helpers.rendering import render_deployment_inventory
from streambuild.executor.deployment.main.load_deployments import load_deployments
from streambuild.executor.deployment.models import DeploymentInventory


def run_deployment_list(
    *,
    database: str,
    metadata_database: str | None,
    json_output: bool,
    client: AdapterConnection,
) -> int:
    """Print authoritative deployment inventory."""
    inventory: DeploymentInventory = load_deployments(
        client=client,
        metadata_database=metadata_database or database,
        default_database=database,
    )
    print(render_deployment_inventory(inventory=inventory, json_output=json_output))
    return 0
