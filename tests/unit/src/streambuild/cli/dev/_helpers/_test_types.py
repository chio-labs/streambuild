from dataclasses import dataclass

from streambuild.dev_server.models import CompileOutcome
from streambuild.dev_server.types import ActivityTone


@dataclass(frozen=True)
class StartupLinesTestCase:
    description: str
    outcome: CompileOutcome
    database: str | None
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ReloadSummaryTestCase:
    description: str
    outcome: CompileOutcome
    expected_status: str
    expected_tone: ActivityTone
    expected_detail: str


@dataclass(frozen=True)
class ActivityLineTestCase:
    description: str
    category: str
    status: str
    tone: ActivityTone
    detail: str
    expected_line: str
