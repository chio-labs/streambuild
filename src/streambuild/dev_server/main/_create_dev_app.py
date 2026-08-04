"""Build the dev server FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.dev_server._helpers.api_routes import register_api_routes
from streambuild.dev_server.classes.build_process import BuildProcessManager
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.silent_reporter import SilentDevServerReporter
from streambuild.dev_server.types import DevServerReporter


def create_dev_app(
    *,
    state: DevServerState,
    connection: AdapterConnection | None = None,
    database: str | None = None,
    project_dir: Path | None = None,
    reporter: DevServerReporter | None = None,
) -> FastAPI:
    """Assemble one application over the shared long-running server state."""

    app: FastAPI = FastAPI(title="StreamBuild", docs_url=None, redoc_url=None)
    active_reporter: DevServerReporter = reporter or SilentDevServerReporter()
    return register_api_routes(
        app=app,
        state=state,
        connection=connection,
        database=database,
        project_dir=project_dir or Path.cwd(),
        builds=BuildProcessManager(reporter=active_reporter),
        reporter=active_reporter,
    )
