"""Recognize deployment-suffixed physical object names."""

from streambuild.compiler.shared.constants import (
    KAFKA_TABLE_NAME_PREFIX,
    MATERIALIZED_VIEW_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
    TRANSFORM_TABLE_NAME_PREFIX,
)

MANAGED_OBJECT_NAME_PREFIXES: tuple[str, ...] = (
    KAFKA_TABLE_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
    TRANSFORM_TABLE_NAME_PREFIX,
    MATERIALIZED_VIEW_NAME_PREFIX,
)


def is_deployment_physical_name(physical_name: str) -> bool:
    """Return whether the name is a StreamBuild deployment-suffixed physical name."""

    logical_name, separator, deployment_id = physical_name.rpartition("__")
    has_deployment_suffix: bool = bool(separator and deployment_id)
    return has_deployment_suffix and logical_name.startswith(MANAGED_OBJECT_NAME_PREFIXES)
