"""Compile-phase runtime domain types."""

from enum import StrEnum


class DesiredObjectType(StrEnum):
    KAFKA_TABLE = "kafka_table"
    TABLE = "table"
    MATERIALIZED_VIEW = "materialized_view"


class LogicalResourceType(StrEnum):
    """Kinds of selectable logical compiler resources."""

    SOURCE = "source"
    MODEL = "model"
