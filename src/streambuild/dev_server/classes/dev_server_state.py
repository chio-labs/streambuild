"""Process-wide dev server state: the held compile plus its guarding locks."""

from __future__ import annotations

import threading
from collections.abc import Callable

from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.server.compile_runner import build_compile_outcome
from streambuild.dev_server.exceptions import ProjectNotCompiledError
from streambuild.dev_server.models import CompileOutcome
from streambuild.dev_server.types import CompileAuthorizationGuard


class DevServerState:
    """One long-running server's source of truth between requests."""

    def __init__(self, *, run_compile: Callable[[], CompileAnalysis]) -> None:
        self._run_compile = run_compile
        self._compile_lock = threading.Lock()
        self._query_lock = threading.Lock()
        self._outcome: CompileOutcome | None = None
        self._servable_outcome: CompileOutcome | None = None
        self._authorization_analysis: CompileAnalysis | None = None

    @property
    def query_lock(self) -> threading.Lock:
        """Serializes warehouse access; the adapter connection is not thread-safe."""

        return self._query_lock

    def reload(self) -> CompileOutcome:
        """Recompile synchronously; concurrent reloads run one at a time."""

        with self._compile_lock:
            return self._reload_locked()

    def reload_guarded(self, *, guard: CompileAuthorizationGuard) -> CompileOutcome:
        """Authorize and recompile atomically against one held policy snapshot."""

        with self._compile_lock:
            _ = guard(analysis=self._authorization_analysis)
            return self._reload_locked()

    def current(self) -> CompileOutcome:
        """Return the held outcome, compiling once on first access."""

        with self._compile_lock:
            if self._outcome is None:
                self._outcome = build_compile_outcome(run_compile=self._run_compile)
                if self._outcome.analysis is not None:
                    self._authorization_analysis = self._outcome.analysis
                    self._servable_outcome = self._outcome
            return self._outcome

    def current_analysis(self) -> CompileAnalysis:
        """Return the latest valid definitions, retaining them across failed reloads."""

        _ = self.current()
        analysis: CompileAnalysis | None = (
            None if self._servable_outcome is None else self._servable_outcome.analysis
        )
        if analysis is None:
            raise ProjectNotCompiledError(
                "The project compile is failing; fix the reported error and reload"
            )
        return analysis

    def current_servable_outcome(self) -> CompileOutcome:
        """Return the latest successful compile outcome or raise before first success."""

        _ = self.current()
        if self._servable_outcome is None:
            raise ProjectNotCompiledError(
                "The project compile is failing; fix the reported error and reload"
            )
        return self._servable_outcome

    def _reload_locked(self) -> CompileOutcome:
        outcome: CompileOutcome = build_compile_outcome(run_compile=self._run_compile)
        self._outcome = outcome
        if outcome.analysis is not None:
            self._authorization_analysis = outcome.analysis
            self._servable_outcome = outcome
        return outcome
