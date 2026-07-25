"""Compile-local physical naming rules."""

from streambuild.compiler.shared.constants import (
    KAFKA_TABLE_NAME_PREFIX,
    MATERIALIZED_VIEW_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
    TRANSFORM_TABLE_NAME_PREFIX,
)


def kafka_table_name(logical_name: str) -> str:
    return f"{KAFKA_TABLE_NAME_PREFIX}{logical_name}"


def raw_table_name(logical_name: str) -> str:
    return f"{RAW_TABLE_NAME_PREFIX}{logical_name}"


def landing_mv_name(logical_name: str) -> str:
    return f"{MATERIALIZED_VIEW_NAME_PREFIX}{logical_name}"


def transform_table_name(logical_name: str) -> str:
    return f"{TRANSFORM_TABLE_NAME_PREFIX}{logical_name}"


def transform_mv_name(logical_name: str) -> str:
    return f"{MATERIALIZED_VIEW_NAME_PREFIX}{logical_name}"
