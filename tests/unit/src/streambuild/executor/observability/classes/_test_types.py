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
