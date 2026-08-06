"""No-op reporter used when nobody is watching the terminal."""

from __future__ import annotations

from pathlib import Path

from streambuild.dev_server.models import CompileOutcome
from streambuild.dev_server.types import ActivityTone


class SilentDevServerReporter:
    """A DevServerReporter that says nothing; the default for embedded use."""

    def report_startup(
        self,
        *,
        outcome: CompileOutcome,
        project_dir: Path,
        database: str | None,
        host: str,
        port: int,
    ) -> None:
        """Ignore the startup banner."""

    def report_reload(self, *, outcome: CompileOutcome) -> None:
        """Ignore the reload outcome."""

    def report_activity(
        self, *, category: str, status: str, tone: ActivityTone, detail: str
    ) -> None:
        """Ignore the activity line."""

    def report_shutdown(self) -> None:
        """Ignore the shutdown line."""
