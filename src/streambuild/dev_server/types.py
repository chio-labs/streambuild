"""Dev server type declarations."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from streambuild.dev_server.models import CompileOutcome


class ActivityTone(StrEnum):
    """How an activity line should read: routine, good news, bad news, or caution."""

    NEUTRAL = "neutral"
    GOOD = "good"
    BAD = "bad"
    CAUTION = "caution"


class DevServerReporter(Protocol):
    """Terminal narrator for the long-running dev server; implemented by the CLI."""

    def report_startup(
        self,
        *,
        outcome: CompileOutcome,
        project_dir: Path,
        database: str | None,
        host: str,
        port: int,
    ) -> None:
        """Print the startup banner for one compiled (or failing) project."""

    def report_reload(self, *, outcome: CompileOutcome) -> None:
        """Print one activity line for a project reload outcome."""

    def report_activity(
        self, *, category: str, status: str, tone: ActivityTone, detail: str
    ) -> None:
        """Print one timestamped activity line."""

    def report_shutdown(self) -> None:
        """Print the shutdown line after the server stops."""


class CompileStateKind(StrEnum):
    """Whether the held project compile is servable or failing."""

    OK = "ok"
    FAILING = "failing"


class ReplayAnchorReason(StrEnum):
    """Why a model is or is not a replay anchor."""

    ELIGIBLE = "eligible"
    AGGREGATE = "aggregate"
    MUTABLE_REF = "mutable_ref"
    NEVER = "never"
    LINEAGE_LOSS = "lineage_loss"
    VIEW = "view"


class Freshness(StrEnum):
    """Derived source or model freshness against its authored policy."""

    FRESH = "fresh"
    LAGGING = "lagging"
    STALLED = "stalled"
