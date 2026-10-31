"""Repair runtime models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairActiveViewRequest:
    """Input required to repair a stable active view."""

    default_database: str
    table_name: str
    deployment_id: str


@dataclass(frozen=True)
class RepairActiveViewResult:
    """Result of explicitly rebinding a stable active view."""

    table_name: str
    target_table_name: str
