"""Single-flight subprocess runner for UI-triggered builds; a pure spectator."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

from streambuild.cli.entry.constants import DEV_CLI_VARIABLES_ENV_VAR
from streambuild.dev_server.exceptions import BuildInProgressError, BuildStartError
from streambuild.dev_server.models import DevExecutionContext
from streambuild.dev_server.types import ActivityTone, DevServerReporter

_RUN_STARTED_KIND: str = "run_started"
_STATEMENT_COMPLETED_KIND: str = "statement_completed"
_START_TIMEOUT_SECONDS: float = 180.0
_STDERR_TAIL_LINES: int = 50


class BuildProcessManager:
    """Owns at most one running `stb build` subprocess and its live event feed."""

    def __init__(
        self, *, reporter: DevServerReporter, execution_context: DevExecutionContext | None = None
    ) -> None:
        self._reporter: DevServerReporter = reporter
        self._lock: threading.Lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._events: list[dict[str, object]] = []
        self._stderr_tail: list[str] = []
        self._invocation_id: str | None = None
        self._exit_code: int | None = None
        self._command: str = ""
        self._started_monotonic: float = 0.0
        self._started_event: threading.Event = threading.Event()
        self._execution_context = execution_context

    def start(
        self,
        *,
        project_dir: Path,
        selectors: tuple[str, ...],
        start_time: str | None,
    ) -> dict[str, object]:
        """Spawn one build and block until its run_started event or early death."""

        argv, command = build_invocation(
            selectors=selectors,
            start_time=start_time,
            execution_context=self._execution_context,
        )
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise BuildInProgressError("a build is already running")
            self._events = []
            self._stderr_tail = []
            self._invocation_id = None
            self._exit_code = None
            self._command = command
            self._started_monotonic = time.monotonic()
            self._started_event = threading.Event()
            self._process = subprocess.Popen(
                argv,
                cwd=project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=_build_environment(execution_context=self._execution_context),
            )
            process: subprocess.Popen[str] = self._process
        threading.Thread(target=self._consume_stdout, args=(process,), daemon=True).start()
        threading.Thread(target=self._consume_stderr, args=(process,), daemon=True).start()
        if not self._started_event.wait(timeout=_START_TIMEOUT_SECONDS):
            raise BuildStartError("timed out waiting for the build's run_started event")
        with self._lock:
            if self._invocation_id is None:
                raise BuildStartError(self._start_failure_message())
            command: str = self._command
        self._reporter.report_activity(
            category="build", status="started", tone=ActivityTone.NEUTRAL, detail=command
        )
        with self._lock:
            return {
                "invocationId": self._invocation_id,
                "command": self._command,
                "status": "running",
            }

    def feed(self, *, after: int) -> dict[str, object]:
        """A cursor read of the live feed: events past `after`, plus run state."""

        with self._lock:
            running: bool = self._process is not None and self._process.poll() is None
            return {
                "running": running,
                "invocationId": self._invocation_id,
                "command": self._command,
                "exitCode": self._exit_code,
                "events": list(self._events[after:]),
                "stderr": "\n".join(self._stderr_tail),
            }

    def _consume_stdout(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            event: dict[str, object] | None = _parsed_event(line)
            if event is None:
                continue
            with self._lock:
                self._events.append(event)
                if event.get("event") == _RUN_STARTED_KIND:
                    self._invocation_id = str(event.get("invocationId"))
            if event.get("event") == _RUN_STARTED_KIND:
                self._started_event.set()
        exit_code: int = process.wait()
        with self._lock:
            self._exit_code = exit_code
            elapsed_seconds: float = time.monotonic() - self._started_monotonic
            statement_count: int = sum(
                1 for item in self._events if item.get("event") == _STATEMENT_COMPLETED_KIND
            )
        self._started_event.set()
        self._report_finished(
            exit_code=exit_code, elapsed_seconds=elapsed_seconds, statement_count=statement_count
        )

    def _consume_stderr(self, process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            with self._lock:
                self._stderr_tail.append(line.rstrip("\n"))
                del self._stderr_tail[:-_STDERR_TAIL_LINES]

    def _report_finished(
        self, *, exit_code: int, elapsed_seconds: float, statement_count: int
    ) -> None:
        succeeded: bool = exit_code == 0
        detail: str = f"{statement_count} statements in {elapsed_seconds:.1f}s"
        if not succeeded:
            detail = f"exit {exit_code} after {elapsed_seconds:.1f}s"
        self._reporter.report_activity(
            category="build",
            status="succeeded" if succeeded else "failed",
            tone=ActivityTone.GOOD if succeeded else ActivityTone.BAD,
            detail=detail,
        )

    def _start_failure_message(self) -> str:
        detail: str = "\n".join(self._stderr_tail).strip()
        exit_note: str = f"build exited with code {self._exit_code} before starting"
        return f"{exit_note}: {detail}" if detail else exit_note


def build_invocation(
    *,
    selectors: tuple[str, ...],
    start_time: str | None,
    execution_context: DevExecutionContext | None,
) -> tuple[list[str], str]:
    """Build the executable argv and safe user-facing command from one source."""
    stb_path: Path = Path(sys.executable).parent / "stb"
    argv: list[str] = [str(stb_path), "build"]
    if execution_context is not None:
        if execution_context.selected_target is not None:
            argv.extend(("--target", execution_context.selected_target))
        if execution_context.database is not None:
            argv.extend(("--database", execution_context.database))
    for selector in selectors:
        argv.extend(("--select", selector))
    if start_time is not None:
        argv.extend(("--start-time", start_time))
    display: str = shlex.join(["stb", *argv[1:]])
    argv.extend(("--auto-approve", "--events"))
    return argv, display


def _build_environment(*, execution_context: DevExecutionContext | None) -> dict[str, str]:
    environment: dict[str, str] = dict(
        os.environ
        if execution_context is None or execution_context.environment is None
        else execution_context.environment
    )
    if execution_context is None:
        return environment
    if execution_context.cli_variables:
        environment[DEV_CLI_VARIABLES_ENV_VAR] = json.dumps(
            dict(execution_context.cli_variables),
            sort_keys=True,
            separators=(",", ":"),
        )
    overrides: tuple[tuple[str, object | None], ...] = (
        ("STREAMBUILD_CLICKHOUSE_HOST", execution_context.connection_host),
        ("STREAMBUILD_CLICKHOUSE_PORT", execution_context.connection_port),
        ("STREAMBUILD_CLICKHOUSE_USERNAME", execution_context.connection_username),
        ("STREAMBUILD_CLICKHOUSE_PASSWORD", execution_context.connection_password),
    )
    for name, value in overrides:
        if value is not None:
            environment[name] = str(value)
    return environment


def _parsed_event(line: str) -> dict[str, object] | None:
    try:
        parsed: object = json.loads(line)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None
