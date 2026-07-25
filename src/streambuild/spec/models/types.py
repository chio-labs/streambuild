"""Authored spec domain types."""

from enum import StrEnum


class ReplayAnchorMode(StrEnum):
    AUTO = "auto"
    NEVER = "never"


class ReplayLineageMode(StrEnum):
    OFFSETS = "offsets"
    TIMESTAMP = "timestamp"
    LANDED_AT = "landed_at"
    CURSOR = "cursor"


class SourceKind(StrEnum):
    KAFKA = "kafka"
    STREAM_TABLE = "stream_table"


class ReplayBoundaryMode(StrEnum):
    OFFSETS = "offsets"
    TIMESTAMP = "timestamp"
    CURSOR = "cursor"


class BoundedReplayFallback(StrEnum):
    FULL_REFRESH = "full_refresh"
    BOUNDED_WITHOUT_HISTORY = "bounded_without_history"


class RefType(StrEnum):
    REFERENCE = "reference"
    MUTABLE = "mutable"


class SqlRelationType(StrEnum):
    SOURCE = "source"
    REF = "ref"


class SchemaChangeBackfillMode(StrEnum):
    FULL = "full"
    BOUNDED = "bounded"


class SchemaChangeKind(StrEnum):
    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
