"""Shared helpers for deployment-specific physical object names."""

from streambuild.compiler.shared.constants import (
    KAFKA_TABLE_NAME_PREFIX,
    MATERIALIZED_VIEW_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
    TRANSFORM_TABLE_NAME_PREFIX,
)


def build_deployment_physical_name(logical_name: str, deployment_id: str) -> str:
    return f"{logical_name}__{deployment_id}"


def is_deployment_physical_name(physical_name: str) -> bool:
    name_parts: tuple[str, str, str] = physical_name.rpartition("__")
    logical_name: str = name_parts[0]
    separator: str = name_parts[1]
    deployment_id: str = name_parts[2]
    return bool(separator and deployment_id) and logical_name.startswith(
        (
            KAFKA_TABLE_NAME_PREFIX,
            RAW_TABLE_NAME_PREFIX,
            TRANSFORM_TABLE_NAME_PREFIX,
            MATERIALIZED_VIEW_NAME_PREFIX,
        )
    )


def deployment_id_from_physical_name(physical_name: str) -> str:
    return physical_name.rsplit("__", 1)[1]


def logical_name_from_physical_name(physical_name: str) -> str:
    return physical_name.rsplit("__", 1)[0]
