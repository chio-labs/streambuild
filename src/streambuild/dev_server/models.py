"""Dev server result models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from streambuild.compiler.pipeline.models import CompilationTimings, CompileAnalysis
from streambuild.dev_server.types import CompileStateKind


@dataclass(frozen=True, repr=False)
class DevExecutionContext:
    """Resolved invocation values retained across dev reloads, previews, and builds."""

    database: str | None = None
    selected_target: str | None = None
    cli_variables: tuple[tuple[str, object], ...] = ()
    environment: Mapping[str, str] | None = None
    connection_host: str | None = None
    connection_port: int | None = None
    connection_username: str | None = None
    connection_password: str | None = None


@dataclass(frozen=True)
class CompileErrorInfo:
    """A compile failure reduced to what an error page needs."""

    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None


@dataclass(frozen=True)
class CompileOutcome:
    """One held project compile: either servable definitions or the failure."""

    state: CompileStateKind
    version_key: str
    compiled_at: str
    analysis: CompileAnalysis | None = None
    timings: CompilationTimings | None = None
    error: CompileErrorInfo | None = None


class ChecksRunRequest(BaseModel):
    """POST /api/checks/run body."""

    kind: str
    name: str


class BuildRunRequest(BaseModel):
    """POST /api/build body."""

    selectors: list[str] = []
    startTime: str | None = None  # noqa: N815 - wire format is camelCase
    confirmations: list[str] = []


class MessageQueryMode(BaseModel):
    """One mutually exclusive message browsing window."""

    kind: str = "newest"
    fromTime: str | None = None  # noqa: N815 - wire format is camelCase
    toTime: str | None = None  # noqa: N815 - wire format is camelCase
    partition: int | None = None
    fromOffset: int | None = None  # noqa: N815 - wire format is camelCase
    toOffset: int | None = None  # noqa: N815 - wire format is camelCase


class MessageQueryPredicate(BaseModel):
    """One typed filter chip compiled to SQL server-side."""

    field: str
    op: str = "eq"
    value: str | int | float | None = None
    values: list[int] = []
    path: list[str | int] = []


class MessageQueryCursor(BaseModel):
    """Keyset pagination position after the last returned row."""

    landedAt: str  # noqa: N815 - wire format is camelCase
    partition: int
    offset: int


class MessagesQueryRequest(BaseModel):
    """POST /api/sources/{name}/messages body."""

    mode: MessageQueryMode = MessageQueryMode()
    predicates: list[MessageQueryPredicate] = []
    limit: int = 50
    cursor: MessageQueryCursor | None = None
    timeColumn: str = "landed"  # noqa: N815 - wire format is camelCase
    previewPaths: list[list[str | int]] = []  # noqa: N815 - wire format is camelCase


class MessageRecordRequest(BaseModel):
    """POST /api/sources/{name}/messages/record body."""

    partition: int
    offset: int


class MessageFacetsRequest(BaseModel):
    """POST /api/sources/{name}/messages/facets body."""

    mode: MessageQueryMode = MessageQueryMode()
    predicates: list[MessageQueryPredicate] = []
    limit: int = 50
    timeColumn: str = "landed"  # noqa: N815 - wire format is camelCase
    facetPath: list[str | int] = []  # noqa: N815 - wire format is camelCase


@dataclass(frozen=True)
class KafkaTopicInfo:
    """Broker metadata for one topic."""

    name: str
    partition_count: int
    replication_factor: int
    internal: bool


@dataclass(frozen=True)
class KafkaTopicsSnapshot:
    """Best-effort topic inventory for one broker list."""

    topics: tuple[KafkaTopicInfo, ...]


@dataclass(frozen=True)
class KafkaPartitionLag:
    """Broker offsets and lag for one topic partition."""

    partition: int
    committed_offset: int | None
    end_offset: int
    lag_messages: int | None


@dataclass(frozen=True)
class KafkaLagSnapshot:
    """Best-effort consumer-group lag for one managed Kafka source."""

    total_messages: int | None
    partitions: tuple[KafkaPartitionLag, ...]
