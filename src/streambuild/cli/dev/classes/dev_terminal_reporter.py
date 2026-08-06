"""Terminal reporter that narrates the dev server session with styled lines."""

from __future__ import annotations

import datetime
import threading
from importlib.metadata import version
from pathlib import Path

from streambuild.cli.dev._helpers.terminal_rendering import (
    activity_line,
    reload_summary,
    startup_lines,
)
from streambuild.cli.presentation.classes.cli_style import CliStyle
from streambuild.dev_server.models import CompileOutcome
from streambuild.dev_server.types import ActivityTone


class DevTerminalReporter:
    """Prints the startup banner and one aligned activity line per server event."""

    def __init__(self, *, style: CliStyle) -> None:
        self._style: CliStyle = style
        self._lock: threading.Lock = threading.Lock()

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

        lines: tuple[str, ...] = startup_lines(
            style=self._style,
            outcome=outcome,
            project_dir=project_dir,
            database=database,
            host=host,
            port=port,
            tool_version=version("streambuild"),
        )
        self._print(text="\n".join(lines))

    def report_reload(self, *, outcome: CompileOutcome) -> None:
        """Print one activity line for a project reload outcome."""

        status: str
        tone: ActivityTone
        detail: str
        status, tone, detail = reload_summary(outcome=outcome)
        self.report_activity(category="reload", status=status, tone=tone, detail=detail)

    def report_activity(
        self, *, category: str, status: str, tone: ActivityTone, detail: str
    ) -> None:
        """Print one timestamped activity line."""

        timestamp: str = datetime.datetime.now().strftime("%H:%M:%S")
        line: str = activity_line(
            style=self._style,
            timestamp=timestamp,
            category=category,
            status=status,
            tone=tone,
            detail=detail,
        )
        self._print(text=line)

    def report_shutdown(self) -> None:
        """Print the shutdown line after the server stops."""

        self._print(text=self._style.muted("dev server stopped"))

    def _print(self, *, text: str) -> None:
        with self._lock:
            print(text, flush=True)
