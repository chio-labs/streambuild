"""Build the deployment-specific physical name for a logical object."""


def build_deployment_physical_name(*, logical_name: str, deployment_id: str) -> str:
    """Return the deployment-suffixed physical name for a logical object."""

    return f"{logical_name}__{deployment_id}"
