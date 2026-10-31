from dataclasses import dataclass

from sqltide.adapter.models import AdapterReplayOffsetFrontier, AdapterReplayOffsetRange
from sqltide.dev_server.models import ReplayOffsetProgress


@dataclass(frozen=True)
class ReplayOffsetProgressCalculationTestCase:
    description: str
    ranges: tuple[AdapterReplayOffsetRange, ...]
    frontiers: tuple[AdapterReplayOffsetFrontier, ...]
    elapsed_seconds: float
    completed: bool
    expected_progress: ReplayOffsetProgress | None


@dataclass(frozen=True)
class ReplayOffsetProgressDecodeTestCase:
    description: str
    metadata: object
    expected_available: bool
