"""Actual-state runtime models."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.shared.models import (
    Column,
    KafkaSettings,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
)


@dataclass(frozen=True)
class ActualKafkaTable:
    """A normalized actual Kafka engine table."""

    key: ObjectKey
    spec: KafkaTableSpec

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def columns(self) -> tuple[Column, ...]:
        return self.spec.columns

    @property
    def kafka(self) -> KafkaSettings:
        return self.spec.kafka


@dataclass(frozen=True)
class ActualTable:
    """A normalized actual managed ClickHouse table."""

    key: ObjectKey
    spec: TableSpec

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def columns(self) -> tuple[Column, ...]:
        return self.spec.columns

    @property
    def engine(self) -> str:
        return self.spec.storage.engine

    @property
    def order_by(self) -> tuple[str, ...]:
        return self.spec.storage.order_by

    @property
    def partition_by(self) -> str | None:
        return self.spec.storage.partition_by

    @property
    def ttl(self) -> str | None:
        return self.spec.storage.ttl

    @property
    def settings(self) -> dict[str, str] | None:
        return self.spec.storage.settings


@dataclass(frozen=True)
class ActualMaterializedView:
    """A normalized actual materialized view."""

    key: ObjectKey
    spec: MaterializedViewSpec

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def source_table_name(self) -> str:
        return self.spec.source_table_name

    @property
    def target_table_name(self) -> str:
        return self.spec.target_table_name

    @property
    def query(self) -> str:
        return self.spec.query


@dataclass(frozen=True)
class ActualState:
    """Project-level flat actual object graph."""

    objects: tuple[ActualKafkaTable | ActualTable | ActualMaterializedView, ...]


@dataclass(frozen=True)
class ObjectStateMetadataRow:
    """Row shape for persisted object-state metadata."""

    deployment_id: str
    database_name: str | None
    object_type: str
    object_name: str
    normalized_fingerprint: str
    normalized_query: str | None
    recorded_at: str


@dataclass(frozen=True)
class TableNameSystemRow:
    """Row shape for system table name lookups."""

    name: str


@dataclass(frozen=True)
class TableColumnSystemRow:
    """Row shape for system column inspection."""

    table_name: str
    name: str
    type: str
    default_expression: str | None


@dataclass(frozen=True)
class TableStorageSystemRow:
    """Row shape for system table storage inspection."""

    table_name: str
    engine: str
    sorting_key: str
    partition_key: str | None
