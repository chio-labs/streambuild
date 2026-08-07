"""Register the JSON API routes on one FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.cli.build.main.build_direct_build_preview import build_direct_build_preview
from streambuild.cli.build.models import DirectBuildPreviewContext, WorkflowPreparationOptions
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.main.normalize_cli_start_time import normalize_cli_start_time
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.dev_server._helpers.checks_execution import (
    build_checks_status_payload,
    run_one_audit,
    run_one_test,
)
from streambuild.dev_server._helpers.compile_runner import build_status_payload
from streambuild.dev_server._helpers.definitions_payload import build_definitions_payload
from streambuild.dev_server._helpers.plan_payload import (
    build_plan_payload,
    count_replay_rows,
)
from streambuild.dev_server._helpers.runs_query import read_active_runs, read_run_events, read_runs
from streambuild.dev_server._helpers.state_payload import build_state_payload
from streambuild.dev_server.classes.build_process import BuildProcessManager, build_invocation
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.exceptions import (
    BuildInProgressError,
    BuildStartError,
    DevServerError,
    ProjectNotCompiledError,
)
from streambuild.dev_server.models import (
    BuildRunRequest,
    ChecksRunRequest,
    CompileOutcome,
    DevExecutionContext,
)
from streambuild.dev_server.types import ActivityTone, DevServerReporter, RunPresentationStatus

_HTTP_BAD_REQUEST: int = 400
_HTTP_CONFLICT: int = 409
_HTTP_BAD_GATEWAY: int = 502
_HTTP_SERVICE_UNAVAILABLE: int = 503


def register_api_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    connection: AdapterConnection | None,
    database: str | None,
    project_dir: Path,
    builds: BuildProcessManager,
    reporter: DevServerReporter,
    execution_context: DevExecutionContext | None = None,
) -> FastAPI:
    """Attach every /api route; handlers close over the shared server state."""

    def read_status() -> dict[str, object]:
        connected: bool = connection is not None
        return build_status_payload(
            outcome=state.current(),
            warehouse_connected=connected,
            warehouse_database=database,
            warehouse_error=None if connected else "no warehouse connection",
        )

    def reload_project() -> dict[str, object]:
        outcome: CompileOutcome = state.reload()
        reporter.report_reload(outcome=outcome)
        return build_status_payload(
            outcome=outcome,
            warehouse_connected=connection is not None,
            warehouse_database=database,
            warehouse_error=None,
        )

    def read_definitions() -> dict[str, object]:
        outcome: CompileOutcome = state.current()
        try:
            analysis: CompileAnalysis = state.current_analysis()
        except ProjectNotCompiledError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        return build_definitions_payload(analysis=analysis, version_key=outcome.version_key)

    def read_state() -> dict[str, object]:
        if connection is None or database is None:
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE,
                detail="no warehouse connection",
            )
        try:
            analysis: CompileAnalysis = state.current_analysis()
        except ProjectNotCompiledError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        try:
            with state.query_lock:
                return build_state_payload(
                    analysis=analysis, connection=connection, database=database
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def _required_connection() -> AdapterConnection:
        if connection is None or database is None:
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE,
                detail="no warehouse connection",
            )
        return connection

    def _servable_analysis() -> CompileAnalysis:
        try:
            return state.current_analysis()
        except ProjectNotCompiledError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error

    def read_plan(
        *,
        select: Annotated[list[str] | None, Query()] = None,
        start: Annotated[str | None, Query()] = None,
    ) -> dict[str, object]:
        client: AdapterConnection = _required_connection()
        analysis: CompileAnalysis = _servable_analysis()
        try:
            if start is not None and not select:
                raise CliUserError("--start-time requires at least one --select")
            normalized_start: str | None = (
                None if start is None else normalize_cli_start_time(start)
            )
            with state.query_lock:
                planned_at: str = client.capture_warehouse_timestamp()
                preview: DirectBuildPreviewContext = build_direct_build_preview(
                    options=WorkflowPreparationOptions(
                        database=database,
                        metadata_database=database,
                        selectors=tuple(select or ()),
                        deployment_id=None,
                        full_refresh=False,
                        start_time=start,
                        verbose=False,
                    ),
                    client=client,
                    analysis=analysis,
                    effective_start_time=normalized_start,
                )
                _, command = build_invocation(
                    selectors=tuple(select or ()),
                    start_time=start,
                    execution_context=execution_context,
                )
                return build_plan_payload(
                    plan=preview.plan,
                    analysis=analysis,
                    selectors=tuple(select or ()),
                    start_time=normalized_start,
                    planned_at=planned_at,
                    command=command,
                    replay_row_counts=count_replay_rows(
                        connection=client,
                        database=preview.database,
                        plan=preview.plan,
                        start_time=normalized_start,
                    ),
                )
        except (CliUserError, DirectPlanError, ValueError) as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    app.get("/api/status")(read_status)
    app.get("/api/state")(read_state)
    app.get("/api/plan")(read_plan)
    app.post("/api/reload")(reload_project)
    app.get("/api/definitions")(read_definitions)
    return _register_quality_routes(
        app=app,
        state=state,
        database=database,
        project_dir=project_dir,
        builds=builds,
        reporter=reporter,
        required_connection=_required_connection,
        servable_analysis=_servable_analysis,
    )


def _register_quality_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    database: str | None,
    project_dir: Path,
    builds: BuildProcessManager,
    reporter: DevServerReporter,
    required_connection: Callable[[], AdapterConnection],
    servable_analysis: Callable[[], CompileAnalysis],
) -> FastAPI:
    """Attach the checks, run-history, and build routes."""

    def run_check(request: ChecksRunRequest) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        analysis: CompileAnalysis = servable_analysis()
        runners: dict[str, Callable[..., dict[str, object]]] = {
            "audit": run_one_audit,
            "test": run_one_test,
        }
        runner: Callable[..., dict[str, object]] | None = runners.get(request.kind)
        if runner is None:
            raise HTTPException(
                status_code=_HTTP_BAD_REQUEST,
                detail="kind must be 'audit' or 'test'",
            )
        try:
            with state.query_lock:
                payload: dict[str, object] = runner(
                    analysis=analysis,
                    connection=client,
                    name=request.name,
                    project_dir=project_dir,
                    database=database or "",
                )
        except DevServerError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        passed: bool = bool(payload.get("passed"))
        reporter.report_activity(
            category=request.kind,
            status="pass" if passed else "fail",
            tone=ActivityTone.GOOD if passed else ActivityTone.BAD,
            detail=request.name,
        )
        return payload

    def read_checks_status() -> list[dict[str, object]]:
        client: AdapterConnection = required_connection()
        analysis: CompileAnalysis = servable_analysis()
        try:
            with state.query_lock:
                return build_checks_status_payload(
                    analysis=analysis,
                    connection=client,
                    database=database or "",
                    project_dir=project_dir,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_run_history() -> list[dict[str, object]]:
        client: AdapterConnection = required_connection()
        try:
            with state.query_lock:
                return read_runs(connection=client, database=database or "")
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_one_run_events(
        *, invocation_id: str, after: Annotated[int, Query(ge=0)] = 0
    ) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        try:
            with state.query_lock:
                return read_run_events(
                    connection=client,
                    database=database or "",
                    invocation_id=invocation_id,
                    after=after,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    app.post("/api/checks/run")(run_check)
    app.get("/api/checks/status")(read_checks_status)
    app.get("/api/runs")(read_run_history)
    app.get("/api/runs/{invocation_id}/events")(read_one_run_events)
    return _register_build_routes(
        app=app,
        builds=builds,
        project_dir=project_dir,
        required_connection=required_connection,
        database=database or "",
        state=state,
    )


def _register_build_routes(
    *,
    app: FastAPI,
    builds: BuildProcessManager,
    project_dir: Path,
    required_connection: Callable[[], AdapterConnection],
    database: str,
    state: DevServerState,
) -> FastAPI:
    """Attach the execute and live-feed routes."""

    def start_build(request: BuildRunRequest) -> dict[str, object]:
        try:
            with state.query_lock:
                blocking_run: dict[str, object] | None = next(
                    (
                        run
                        for run in read_active_runs(
                            connection=required_connection(), database=database
                        )
                        if run["status"]
                        in {
                            RunPresentationStatus.RUNNING,
                            RunPresentationStatus.UNRESPONSIVE,
                        }
                    ),
                    None,
                )
            if blocking_run is not None:
                raise BuildInProgressError(
                    f"run {blocking_run['invocationId']} is {blocking_run['status']} "
                    f"(last signal {blocking_run['lastSignalAgeSeconds']}s ago)"
                )
            return builds.start(
                project_dir=project_dir,
                selectors=tuple(request.selectors),
                start_time=request.startTime,
            )
        except BuildInProgressError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        except BuildStartError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error

    def read_build_feed(*, after: Annotated[int, Query(ge=0)] = 0) -> dict[str, object]:
        return builds.feed(after=after)

    def cancel_build(request: dict[str, str]) -> dict[str, object]:
        try:
            return builds.cancel(invocation_id=request.get("invocationId", ""))
        except BuildInProgressError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error

    def kill_build(request: dict[str, str]) -> dict[str, object]:
        try:
            return builds.kill(invocation_id=request.get("invocationId", ""))
        except BuildInProgressError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error

    app.post("/api/build")(start_build)
    app.get("/api/build/current")(read_build_feed)
    app.post("/api/build/cancel")(cancel_build)
    app.post("/api/build/kill")(kill_build)
    return app
