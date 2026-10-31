"""SQL reference vocabulary."""

from enum import StrEnum


class RefType(StrEnum):
    REFERENCE = "reference"
    MUTABLE = "mutable"


class SqlRelationType(StrEnum):
    SOURCE = "source"
    REF = "ref"


class SqlQueryShape(StrEnum):
    """The supported outer shape of an authored model query."""

    SELECT = "select"


class SqlStorageExpressionKind(StrEnum):
    """One model storage clause analyzed against its output schema."""

    ORDER_BY = "order_by"
    PARTITION_BY = "partition_by"
    TTL = "ttl"


type NativeReference = tuple[str, str, str | None, int, int]


class SqlTreeErrorKind(StrEnum):
    """Which SQL analysis exception one native tree-analysis failure becomes."""

    ANALYSIS = "analysis"
    STATEMENT_COUNT = "statement_count"
    QUERY_SHAPE = "query_shape"
    UNTYPED_PROJECTION = "untyped_projection"
    STAR_PROJECTION = "star_projection"
    DUPLICATE_ALIAS = "duplicate_alias"
