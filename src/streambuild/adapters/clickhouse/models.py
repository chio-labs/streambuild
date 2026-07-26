"""ClickHouse system-row models used while assembling a neutral catalog."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClickHouseCatalogRelationRow:
    name: str
    engine: str
    sorting_key: str
    partition_key: str
    create_table_query: str
    as_select: str


@dataclass(frozen=True)
class ClickHouseCatalogColumnRow:
    table_name: str
    name: str
    type: str
    default_expression: str | None


@dataclass(frozen=True)
class ActiveBindingSystemRow:
    """One stable view binding read from ClickHouse system tables."""

    name: str
    as_select: str


@dataclass(frozen=True)
class PhysicalCandidateSystemRow:
    """One deployment-suffixed physical table candidate."""

    name: str
