"""Deployment diff public entrypoint."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.deployment._helpers.diff import execute_diff
from streambuild.executor.deployment.models import DeploymentDiffRequest, DeploymentDiffResult


def execute_deployment_diff(
    *, request: DeploymentDiffRequest, client: AdapterConnection
) -> DeploymentDiffResult:
    """Compare active or retained deployment relations."""

    return execute_diff(request=request, client=client)
