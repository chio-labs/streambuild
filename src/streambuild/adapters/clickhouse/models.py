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


@dataclass(frozen=True)
class ClickHouseMetadataStatement:
    """A ClickHouse metadata insert statement and its row mappings."""

    table: str
    sql: str
    rows: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class ClickHouseReplayOffsetFrontier:
    """One partition frontier used for bounded offset replay."""

    partition: object
    cutoff_offset: str


@dataclass(frozen=True)
class ClickHouseReplayColumn:
    """One ClickHouse relation column needed during replay realization."""

    name: str
    type: str
