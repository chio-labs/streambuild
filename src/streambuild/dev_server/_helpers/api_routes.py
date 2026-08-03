"""Register the JSON API routes on one FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.definitions_payload import build_definitions_payload
from streambuild.dev_server._helpers.status_payload import build_status_payload
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.exceptions import ProjectNotCompiledError
from streambuild.dev_server.models import CompileOutcome

_HTTP_CONFLICT: int = 409


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

    app.get("/api/status")(read_status)
    app.post("/api/reload")(reload_project)
    app.get("/api/definitions")(read_definitions)
    return app
