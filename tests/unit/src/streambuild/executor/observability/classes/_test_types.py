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
