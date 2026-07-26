"""Extract the deployment identifier from a deployment-suffixed physical name."""


def deployment_id_from_physical_name(physical_name: str) -> str:
    """Return the deployment identifier encoded in a physical object name."""

    return physical_name.rsplit("__", 1)[1]
