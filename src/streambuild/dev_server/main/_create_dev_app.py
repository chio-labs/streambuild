"""Build the dev server FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.dev_server._helpers.api_routes import register_api_routes
from streambuild.dev_server.classes.dev_server_state import DevServerState


def create_dev_app(
    *,
    state: DevServerState,
    connection: AdapterConnection | None = None,
    database: str | None = None,
    project_dir: Path | None = None,
) -> FastAPI:
    """Assemble one application over the shared long-running server state."""

    app: FastAPI = FastAPI(title="StreamBuild", docs_url=None, redoc_url=None)
    return register_api_routes(
        app=app,
        state=state,
        connection=connection,
        database=database,
        project_dir=project_dir or Path.cwd(),
    )
