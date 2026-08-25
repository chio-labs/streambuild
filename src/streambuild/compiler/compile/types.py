"""Compile-phase runtime domain types."""

from enum import StrEnum


class DesiredObjectType(StrEnum):
    KAFKA_TABLE = "kafka_table"
    TABLE = "table"
    MATERIALIZED_VIEW = "materialized_view"
    VIEW = "view"


class LogicalResourceType(StrEnum):
    """Kinds of selectable logical compiler resources."""

    SOURCE = "source"
    MODEL = "model"


class RetentionOrigin(StrEnum):
    MODEL = "model"
    PIPELINE = "pipeline"
    PROJECT = "project"
