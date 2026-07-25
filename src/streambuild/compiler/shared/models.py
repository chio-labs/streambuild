"""Shared compiler models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.shared.types import DesiredObjectType
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.project import Project
from streambuild.spec.models.steps import SchemaChangeBackfillPolicy
from streambuild.spec.models.types import BoundedReplayFallback, SqlRelationType


@dataclass(frozen=True)
class ObjectKey:
    """Stable identity for a comparable deployed object."""

    database: str | None
    object_type: DesiredObjectType | str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "object_type", DesiredObjectType(self.object_type))


@dataclass(frozen=True)
class Column:
    """A normalized comparable column definition."""

    name: str
    type: str
    default: str | None = None


@dataclass(frozen=True)
class KafkaSettings:
    """Normalized comparable Kafka engine settings."""

    broker_list: str
    topic: str
    consumer_group: str
    format: str
    settings: dict[str, str] | None = None


@dataclass(frozen=True)
class KafkaTableSpec:
    """Comparable Kafka table specification."""

    columns: tuple[Column, ...]
    kafka: KafkaSettings


@dataclass(frozen=True)
class TableStorage:
    """Comparable managed-table storage definition."""

    engine: str
    order_by: tuple[str, ...]
    partition_by: str | None = None
    ttl: str | None = None
    settings: dict[str, str] | None = None


@dataclass(frozen=True)
class TableSpec:
    """Comparable managed-table specification."""

    columns: tuple[Column, ...]
    storage: TableStorage


@dataclass(frozen=True)
class MaterializedViewSpec:
    """Comparable materialized-view specification."""

    source_table_name: str
    target_table_name: str
    query: str


@dataclass(frozen=True)
class DesiredKafkaTable:
    """A desired Kafka engine table for a landing step."""

    key: ObjectKey
    deps: tuple[ObjectKey, ...]
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
class DesiredTable:
    """A desired managed ClickHouse table."""

    key: ObjectKey
    deps: tuple[ObjectKey, ...]
    spec: TableSpec
    schema_change_backfill: SchemaChangeBackfillPolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback = BoundedReplayFallback(
        BoundedReplayFallback.FULL_REFRESH
    )

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
class DesiredMaterializedView:
    """A desired materialized view between a source and target relation."""

    key: ObjectKey
    deps: tuple[ObjectKey, ...]
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
class LoadedPipeline:
    """A discovered pipeline plus the file it was loaded from."""

    pipeline: Pipeline
    file_path: Path
    project: Project | None = None


@dataclass(frozen=True)
class SqlTestMock:
    """One discovered direct mock boundary in a SQL test file."""

    cte_name: str
    name: str
    relation_type: SqlRelationType | str
    query: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_type", SqlRelationType(self.relation_type))


@dataclass(frozen=True)
class SqlTestCte:
    """One authored CTE preserved from a SQL-native test file."""

    name: str
    query: str


@dataclass(frozen=True)
class LoadedSqlTest:
    """One discovered SQL test file with extracted mock and expectation CTEs."""

    file_path: Path
    authored_ctes: tuple[SqlTestCte, ...]
    mocks: tuple[SqlTestMock, ...]
    expected_targets: tuple[SqlTestCte, ...]
    name: str | None = None
    test_index: int = 1


@dataclass(frozen=True)
class LoadedSqlAudit:
    """One discovered SQL audit file with validated metadata and refs."""

    file_path: Path
    query: str
    referenced_model_names: tuple[str, ...]
    severity: str = "error"
    description: str | None = None
    name: str | None = None
    audit_index: int = 1


@dataclass(frozen=True)
class LoadedGenericSqlAuditDefinition:
    """One reusable generic SQL audit definition discovered from `audits/generic/`."""

    file_path: Path
    query: str
    raw_parameter_names: tuple[str, ...]
    quoted_parameter_names: tuple[str, ...]
    name: str


@dataclass(frozen=True)
class LoadedGenericSqlAuditInstance:
    """One schema-attached generic SQL audit before template rendering."""

    file_path: Path
    definition_name: str
    arguments: dict[str, object]
    name: str
    severity: str = "error"
    description: str | None = None
