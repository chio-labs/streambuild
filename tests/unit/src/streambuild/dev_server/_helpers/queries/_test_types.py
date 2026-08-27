from dataclasses import dataclass

from streambuild.adapter.models import AdapterReplayOffsetFrontier, AdapterReplayOffsetRange
from streambuild.dev_server.models import ReplayOffsetProgress


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
