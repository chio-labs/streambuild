"""CLI command for deployment comparison."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.deployment._helpers.diff_rendering import render_deployment_diff
from streambuild.executor.deployment.main.execute_deployment_diff import execute_deployment_diff
from streambuild.executor.deployment.models import DeploymentDiffRequest, DeploymentDiffResult


def run_deployment_diff(
    *,
    database: str,
    metadata_database: str | None,
    comparison: str,
    json_output: bool,
    client: AdapterConnection,
) -> int:
    """Compare two deployment endpoints and print their differences."""

    result: DeploymentDiffResult = execute_deployment_diff(
        request=DeploymentDiffRequest(
            database=database,
            metadata_database=metadata_database or database,
            comparison=comparison,
        ),
        client=client,
    )
    print(render_deployment_diff(result=result, json_output=json_output))
    return 0
