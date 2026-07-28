"""Immutable SQL analysis facts."""

from dataclasses import dataclass

from streambuild.compiler.sql_analysis.types import (
    RefType,
    SqlLineageConfidence,
    SqlQueryShape,
    SqlRelationType,
    SqlStorageExpressionKind,
)


@dataclass(frozen=True)
class SqlSourceSpan:
    """One half-open source span with one-based display coordinates."""

    start: int
    end: int
    line: int
    column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class SqlReference:
    """One authored logical relation reference."""

    name: str
    relation_type: SqlRelationType | str
    span: SqlSourceSpan
    ref_type: RefType | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_type", SqlRelationType(self.relation_type))


@dataclass(frozen=True)
class SqlCommonTableExpression:
    """One authored top-level common table expression and its verbatim body."""

    name: str
    query: str
    span: SqlSourceSpan


@dataclass(frozen=True)
class SqlTopLevelCtes:
    """Authored top-level CTEs plus the statement text that follows them."""

    ctes: tuple[SqlCommonTableExpression, ...]
    trailing_sql: str
    trailing_span: SqlSourceSpan


@dataclass(frozen=True)
class SqlOutputColumn:
    """One exact typed output from the outer model projection list."""

    name: str
    type: str


@dataclass(frozen=True)
class SqlLineageSourceFact:
    """One compact upstream column contributing to a model output."""

    relation_name: str
    column_name: str
    confidence: SqlLineageConfidence | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", SqlLineageConfidence(self.confidence))


@dataclass(frozen=True)
class SqlProjection:
    """One strict outer projection and its compact lineage facts."""

    index: int
    sql: str
    output: SqlOutputColumn
    span: SqlSourceSpan
    upstream: tuple[SqlLineageSourceFact, ...]


@dataclass(frozen=True)
class SqlStorageExpression:
    """One canonical storage expression and its output-column references."""

    kind: SqlStorageExpressionKind | str
    sql: str
    canonical_sql: str
    referenced_column_names: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", SqlStorageExpressionKind(self.kind))


@dataclass(frozen=True)
class SqlAggregateFacts:
    """ClickHouse query and engine aggregation facts for one model."""

    has_group_by: bool
    function_names: tuple[str, ...]
    engine_name: str
    engine_has_aggregate_semantics: bool

    @property
    def has_semantics(self) -> bool:
        return self.has_group_by or bool(self.function_names) or self.engine_has_aggregate_semantics


@dataclass(frozen=True)
class SqlModelAnalysis:
    """Complete immutable SQL facts produced once for one authored model."""

    authored_sql: str
    canonical_sql: str
    shape: SqlQueryShape | str
    projections: tuple[SqlProjection, ...]
    references: tuple[SqlReference, ...]
    storage_expressions: tuple[SqlStorageExpression, ...]
    aggregate_facts: SqlAggregateFacts

    def __post_init__(self) -> None:
        object.__setattr__(self, "shape", SqlQueryShape(self.shape))

    @property
    def output_columns(self) -> tuple[SqlOutputColumn, ...]:
        return tuple(projection.output for projection in self.projections)


@dataclass(frozen=True)
class SqlResolvedQuery:
    """Canonical database-neutral SQL and its adapter database template."""

    canonical_sql: str
    database_template: str


@dataclass(frozen=True)
class SqlRelationRewrite:
    """One eligible relation identity and its replacement relation SQL."""

    source_name: str
    target_relation: str
    source_databases: tuple[str | None, ...] | None = None
    preserve_source_database: bool = False


@dataclass(frozen=True)
class SqlNamedQuery:
    """One named query to prepend to a rewritten SELECT."""

    name: str
    query: str


@dataclass(frozen=True)
class SqlQueryRewriteResult:
    """Canonical rewritten SELECT SQL and its aggregate classification."""

    query: str
    has_aggregate_semantics: bool


@dataclass(frozen=True)
class SqlRelationIdentity:
    """One physical SQL relation identity."""

    database: str | None
    name: str


@dataclass(frozen=True)
class SqlCatalogAnalysis:
    """Canonical query and ClickHouse catalog facts from one SQL statement."""

    canonical_sql: str
    query_sql: str | None
    first_source: SqlRelationIdentity | None
    direct_source: SqlRelationIdentity | None
    target_relation: SqlRelationIdentity | None
    ttl: str | None
    settings: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SqlHeaderBlock:
    """One lexically isolated SQL extension header and following body."""

    start: int
    body_start: int
    header: str
    body: str
