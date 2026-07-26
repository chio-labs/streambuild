"""Recognize deployment-suffixed physical object names."""

from streambuild.compiler.shared.constants import MANAGED_OBJECT_NAME_PREFIXES


def is_deployment_physical_name(physical_name: str) -> bool:
    """Return whether the name is a StreamBuild deployment-suffixed physical name."""

    logical_name, separator, deployment_id = physical_name.rpartition("__")
    has_deployment_suffix: bool = bool(separator and deployment_id)
    return has_deployment_suffix and logical_name.startswith(MANAGED_OBJECT_NAME_PREFIXES)
