"""Single-flight subprocess runner for UI-triggered builds; a pure spectator."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import IO
from uuid import uuid4

from streambuild.cli.entry.constants import DEV_CLI_VARIABLES_ENV_VAR
from streambuild.dev_server.constants import CANCEL_GRACE_SECONDS, TERMINATE_GRACE_SECONDS
from streambuild.dev_server.exceptions import BuildInProgressError, BuildStartError
from streambuild.dev_server.models import DevExecutionContext
from streambuild.dev_server.types import ActivityTone, DevServerReporter
from streambuild.executor.observability.constants import (
    RUN_DISPLAY_COMMAND_ENV_VAR,
    RUN_INVOCATION_ID_ENV_VAR,
)

_RUN_STARTED_KIND: str = "run_started"
_STATEMENT_COMPLETED_KIND: str = "statement_completed"
_STDERR_TAIL_LINES: int = 50


class BuildProcessManager:
    """Owns at most one running `stb build` subprocess and its live event feed."""

    def __init__(
        self, *, reporter: DevServerReporter, execution_context: DevExecutionContext | None = None
    ) -> None:
        self._reporter: DevServerReporter = reporter
        self._lock: threading.Lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._statement_count: int = 0
        self._stderr_path: Path | None = None
        self._invocation_id: str | None = None
        self._exit_code: int | None = None
        self._command: str = ""
        self._started_monotonic: float = 0.0
        self._current_invocation_id: str | None = None
        self._cancelling_invocation_id: str | None = None
        self._force_available: bool = False
        self._execution_context = execution_context

    def start(
        self,
        *,
        project_dir: Path,
        selectors: tuple[str, ...],
        start_time: str | None,
        deployment_id: str | None = None,
        confirmations: tuple[str, ...] = (),
    ) -> dict[str, object]:
        """Spawn one build and return its stable launch identity immediately."""

        argv, command = build_invocation(
            selectors=selectors,
            start_time=start_time,
            deployment_id=deployment_id,
            confirmations=confirmations,
            execution_context=self._execution_context,
        )
        launch_invocation_id: str = str(uuid4())
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise BuildInProgressError("a build is already running")
            self._statement_count = 0
            self._remove_stderr_file()
            self._invocation_id = launch_invocation_id
            self._current_invocation_id = None
            self._cancelling_invocation_id = None
            self._force_available = False
            self._exit_code = None
            self._command = command
            self._started_monotonic = time.monotonic()
            stderr_file: IO[str] = tempfile.NamedTemporaryFile(
                mode="w+", prefix="streambuild-run-", suffix=".stderr", delete=False
            )
            self._stderr_path = Path(stderr_file.name)
            try:
                self._process = subprocess.Popen(
                    argv,
                    cwd=project_dir,
                    stdout=subprocess.PIPE,
                    stderr=stderr_file,
                    text=True,
                    env=_build_environment(
                        execution_context=self._execution_context,
                        display_command=command,
                        invocation_id=launch_invocation_id,
                    ),
                )
            except OSError as error:
                stderr_file.close()
                self._remove_stderr_file()
                self._invocation_id = None
                self._command = ""
                raise BuildStartError(str(error)) from error
            stderr_file.close()
            process: subprocess.Popen[str] = self._process
        threading.Thread(
            target=self._consume_stdout,
            kwargs={"process": process, "launch_invocation_id": launch_invocation_id},
            daemon=True,
        ).start()
        self._reporter.report_activity(
            category="build", status="starting", tone=ActivityTone.NEUTRAL, detail=command
        )
        return {
            "invocationId": launch_invocation_id,
            "command": command,
            "status": "starting",
        }

    def feed(self, *, after: int) -> dict[str, object]:
        """A cursor read of the live feed: events past `after`, plus run state."""

        del after
        with self._lock:
            running: bool = self._process is not None and self._process.poll() is None
            return {
                "running": running,
                "invocationId": self._invocation_id,
                "currentInvocationId": self._current_invocation_id,
                "command": self._command,
                "exitCode": self._exit_code,
                "events": [],
                "stderr": self._read_stderr_tail(),
                "forceAvailable": self._force_available,
            }

    def cancel(self, *, invocation_id: str) -> dict[str, object]:
        """Request graceful cancellation of the server-owned child."""

        with self._lock:
            if self._cancelling_invocation_id == invocation_id:
                return {
                    "status": "cancelling",
                    "forceAvailable": self._force_available,
                }
            process: subprocess.Popen[str] = self._owned_process_locked(invocation_id=invocation_id)
            self._cancelling_invocation_id = invocation_id
        process.send_signal(signal.SIGINT)
        try:
            exit_code: int = process.wait(timeout=CANCEL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                exit_code = process.wait(timeout=TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                with self._lock:
                    self._force_available = True
                return {"status": "cancelling", "forceAvailable": True}
        with self._lock:
            self._force_available = False
        return {"status": "cancelled", "exitCode": exit_code, "forceAvailable": False}

    def kill(self, *, invocation_id: str) -> dict[str, object]:
        """Force-kill the server-owned child without fabricating terminal facts."""

        process: subprocess.Popen[str] = self._owned_process(invocation_id=invocation_id)
        process.kill()
        with self._lock:
            self._force_available = False
        return {"status": "killed"}

    def _consume_stdout(self, *, process: subprocess.Popen[str], launch_invocation_id: str) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            event: dict[str, object] | None = _parsed_event(line)
            if event is None:
                continue
            with self._lock:
                if process is not self._process or self._invocation_id != launch_invocation_id:
                    continue
                if event.get("event") == _RUN_STARTED_KIND:
                    self._current_invocation_id = str(event.get("invocationId"))
                if event.get("event") == _STATEMENT_COMPLETED_KIND:
                    self._statement_count += 1
        exit_code: int = process.wait()
        with self._lock:
            if process is not self._process or self._invocation_id != launch_invocation_id:
                return
            self._exit_code = exit_code
            self._force_available = False
            elapsed_seconds: float = time.monotonic() - self._started_monotonic
            statement_count: int = self._statement_count
        self._report_finished(
            exit_code=exit_code, elapsed_seconds=elapsed_seconds, statement_count=statement_count
        )

    def _read_stderr_tail(self) -> str:
        path: Path | None = self._stderr_path
        if path is None or not path.exists():
            return ""
        return "\n".join(
            path.read_text(encoding="utf-8", errors="replace").splitlines()[-_STDERR_TAIL_LINES:]
        )

    def _remove_stderr_file(self) -> None:
        path: Path | None = self._stderr_path
        if path is not None:
            path.unlink(missing_ok=True)
        self._stderr_path = None

    def _owned_process(self, *, invocation_id: str) -> subprocess.Popen[str]:
        with self._lock:
            return self._owned_process_locked(invocation_id=invocation_id)

    def _owned_process_locked(self, *, invocation_id: str) -> subprocess.Popen[str]:
        process: subprocess.Popen[str] | None = self._process
        if self._invocation_id != invocation_id or process is None or process.poll() is not None:
            raise BuildInProgressError(
                "this server does not own that running process; "
                "it cannot deliver a cancellation signal"
            )
        return process

    def close(self) -> None:
        """Release server-owned temporary evidence without signalling the child."""

        with self._lock:
            self._remove_stderr_file()

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


def build_invocation(
    *,
    selectors: tuple[str, ...],
    start_time: str | None,
    deployment_id: str | None = None,
    execution_context: DevExecutionContext | None,
    confirmations: tuple[str, ...] = (),
) -> tuple[list[str], str]:
    """Build the executable argv and safe user-facing command from one source."""
    stb_path: Path = Path(sys.executable).parent / "stb"
    argv: list[str] = [str(stb_path), "build"]
    display_argv: list[str] = ["stb", "build"]
    if execution_context is not None:
        if execution_context.selected_target is not None:
            argv.extend(("--target", execution_context.selected_target))
        if execution_context.database is not None:
            argv.extend(("--database", execution_context.database))
    if selectors:
        argv.extend(("--select", *selectors))
        display_argv.extend(("--select", *selectors))
    if start_time is not None:
        argv.extend(("--start-time", start_time))
        display_argv.extend(("--start-time", start_time))
    if deployment_id is not None:
        argv.extend(("--deployment-id", deployment_id))
        display_argv.extend(("--deployment-id", deployment_id))
    for confirmation in confirmations:
        argv.extend(("--confirm", confirmation))
        display_argv.extend(("--confirm", confirmation))
    display: str = shlex.join(display_argv)
    argv.extend(("--auto-approve", "--events"))
    return argv, display


def _build_environment(
    *,
    execution_context: DevExecutionContext | None,
    display_command: str | None = None,
    invocation_id: str | None = None,
) -> dict[str, str]:
    environment: dict[str, str] = dict(
        os.environ
        if execution_context is None or execution_context.environment is None
        else execution_context.environment
    )
    if display_command is not None:
        environment[RUN_DISPLAY_COMMAND_ENV_VAR] = display_command
    if invocation_id is not None:
        environment[RUN_INVOCATION_ID_ENV_VAR] = invocation_id
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
