"""Show one virtual deployment."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.deployment._helpers.rendering import render_deployment
from streambuild.executor.deployment.main.load_deployment import load_deployment
from streambuild.executor.deployment.models import DeploymentSummary


def run_deployment_show(
    *,
    deployment_id: str,
    database: str,
    metadata_database: str | None,
    json_output: bool,
    client: AdapterConnection,
) -> int:
    """Print one authoritative deployment summary."""
    deployment: DeploymentSummary = load_deployment(
        deployment_id=deployment_id,
        client=client,
        metadata_database=metadata_database or database,
        default_database=database,
    )
    print(render_deployment(deployment=deployment, database=database, json_output=json_output))
    return 0
