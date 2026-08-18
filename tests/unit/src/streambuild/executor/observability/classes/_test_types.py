from dataclasses import dataclass


@dataclass(frozen=True)
class RunEventSinkTestCase:
    description: str
    expected_event_kinds: tuple[str, ...]
    expected_sequences: tuple[int, ...]
    expected_persisted_markers: tuple[str, ...]


@dataclass(frozen=True)
class RunEventHeartbeatTestCase:
    description: str
    expected_event_kind: str


@dataclass(frozen=True)
class RunEventDisplayCommandTestCase:
    description: str
    command: str
    environment_command: str
    explicit_command: str | None
    expected_command: str


@dataclass(frozen=True)
class RunEventScopeTestCase:
    description: str
    expected_executed_logical_ids: tuple[str, ...]
    expected_context_logical_ids: tuple[str, ...]


@dataclass(frozen=True)
class RunEventStartupTimingsTestCase:
    description: str
    compile_ms: int
    observability_ms: int
    planning_ms: int
    expected_total_ms: int


@dataclass(frozen=True)
class RunStatementPersistenceTestCase:
    description: str
    invocation_id: str
    workflow_sha256: str
    expected_sql: str
    expected_insert_marker: str
    expected_verify_fragment: str


@dataclass(frozen=True)
class RunStatementRedactionTestCase:
    description: str
    invocation_id: str
    sql: str
    expected_absent_fragments: tuple[str, ...]
    expected_redacted_count: int
    expected_present_fragment: str


@dataclass(frozen=True)
class RunStatementUnsupportedTestCase:
    description: str
    invocation_id: str
    workflow_sha256: str
    expected_executed_statements: tuple[str, ...]
