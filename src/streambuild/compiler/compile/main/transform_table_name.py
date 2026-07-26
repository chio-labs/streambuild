"""Derive the physical transform table name for a logical model."""

from streambuild.compiler.shared.constants import (
    TRANSFORM_TABLE_NAME_PREFIX,
)


def transform_table_name(logical_name: str) -> str:
    return f"{TRANSFORM_TABLE_NAME_PREFIX}{logical_name}"
