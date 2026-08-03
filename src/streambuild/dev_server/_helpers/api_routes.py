"""Register the JSON API routes on one FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
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
from streambuild.dev_server._helpers.checks_execution import run_one_audit, run_one_test
from streambuild.dev_server._helpers.definitions_payload import build_definitions_payload
from streambuild.dev_server._helpers.plan_payload import build_plan_payload, expand_selectors
from streambuild.dev_server._helpers.runs_query import read_runs
from streambuild.dev_server._helpers.state_payload import build_state_payload
from streambuild.dev_server._helpers.status_payload import build_status_payload
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
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        return build_plan_payload(
            plan=plan,
            analysis=analysis,
            selectors=tuple(select or ()),
            start_time=start,
            planned_at=planned_at,
        )

    def run_check(request: ChecksRunRequest) -> dict[str, object]:
        client: AdapterConnection = _required_connection()
        analysis: CompileAnalysis = _servable_analysis()
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
                return runner(analysis=analysis, connection=client, name=request.name)
        except DevServerError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_run_history() -> list[dict[str, object]]:
        client: AdapterConnection = _required_connection()
        try:
            with state.query_lock:
                return read_runs(connection=client, database=database or "")
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    app.get("/api/status")(read_status)
    app.get("/api/state")(read_state)
    app.get("/api/plan")(read_plan)
    app.post("/api/checks/run")(run_check)
    app.get("/api/runs")(read_run_history)
    app.post("/api/reload")(reload_project)
    app.get("/api/definitions")(read_definitions)
    return app
