"""Process-wide dev server state: the held compile plus its guarding locks."""

from __future__ import annotations

import threading
from collections.abc import Callable

from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.compile_runner import build_compile_outcome
from streambuild.dev_server.exceptions import ProjectNotCompiledError
from streambuild.dev_server.models import CompileOutcome


class DevServerState:
    """One long-running server's source of truth between requests."""

    def __init__(self, *, run_compile: Callable[[], CompileAnalysis]) -> None:
        self._run_compile = run_compile
        self._compile_lock = threading.Lock()
        self._query_lock = threading.Lock()
        self._outcome: CompileOutcome | None = None

    @property
    def query_lock(self) -> threading.Lock:
        """Serializes warehouse access; the adapter connection is not thread-safe."""

        return self._query_lock

    def reload(self) -> CompileOutcome:
        """Recompile synchronously; concurrent reloads run one at a time."""

        with self._compile_lock:
            outcome: CompileOutcome = build_compile_outcome(run_compile=self._run_compile)
            self._outcome = outcome
            return outcome

    def current(self) -> CompileOutcome:
        """Return the held outcome, compiling once on first access."""

        with self._compile_lock:
            if self._outcome is None:
                self._outcome = build_compile_outcome(run_compile=self._run_compile)
            return self._outcome

    def current_analysis(self) -> CompileAnalysis:
        """Return servable definitions or raise when the compile is failing."""

        outcome: CompileOutcome = self.current()
        if outcome.analysis is None:
            raise ProjectNotCompiledError(
                "The project compile is failing; fix the reported error and reload"
            )
        return outcome.analysis
