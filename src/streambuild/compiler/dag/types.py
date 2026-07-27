"""Logical DAG artifact type declarations."""

from enum import StrEnum


class DagNodeType(StrEnum):
    """Kinds of logical nodes emitted in the StreamBuild DAG."""

    SOURCE = "source"
    MODEL = "model"
    TEST = "test"
    AUDIT = "audit"


class DagCheckEdgeType(StrEnum):
    """Check relationships added beyond model lineage edges."""

    TEST = "test"
    AUDIT = "audit"
