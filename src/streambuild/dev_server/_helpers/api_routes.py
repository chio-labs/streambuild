"""Register the JSON API routes on one FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.main.load_direct_warehouse_snapshot import (
    load_direct_warehouse_snapshot,
)
from streambuild.compiler.planner.main.plan_direct_build import plan_direct_build
from streambuild.compiler.planner.models import DirectPlan, DirectWarehouseSnapshot
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
    expand_selectors,
)
from streambuild.dev_server._helpers.runs_query import read_runs
from streambuild.dev_server._helpers.state_payload import build_state_payload
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.exceptions import DevServerError, ProjectNotCompiledError
from streambuild.dev_server.models import ChecksRunRequest, CompileOutcome

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
            selected: frozenset = expand_selectors(analysis=analysis, selectors=tuple(select or ()))
        except DevServerError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        try:
            with state.query_lock:
                planned_at: str = client.capture_warehouse_timestamp()
                snapshot: DirectWarehouseSnapshot = load_direct_warehouse_snapshot(
                    client=client,
                    database=database or "",
                    metadata_database=database or "",
                )
                plan: DirectPlan = plan_direct_build(
                    graph=analysis.graph,
                    realized_project=analysis.realized_project,
                    snapshot=snapshot,
                    database=database or "",
                    selected_model_keys=selected,
                    effective_start_time=start,
                )
                return build_plan_payload(
                    plan=plan,
                    analysis=analysis,
                    selectors=tuple(select or ()),
                    start_time=start,
                    planned_at=planned_at,
                    replay_row_counts=count_replay_rows(
                        connection=client,
                        database=database or "",
                        plan=plan,
                        start_time=start,
                    ),
                )
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
        required_connection=_required_connection,
        servable_analysis=_servable_analysis,
    )


def _register_quality_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    database: str | None,
    project_dir: Path,
    required_connection: Callable[[], AdapterConnection],
    servable_analysis: Callable[[], CompileAnalysis],
) -> FastAPI:
    """Attach the checks and run-history routes."""

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
                return runner(
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

    app.post("/api/checks/run")(run_check)
    app.get("/api/checks/status")(read_checks_status)
    app.get("/api/runs")(read_run_history)
    return app
