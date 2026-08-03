"""Start the long-running dev server over one compiled project."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.static_assets import (
    register_static_assets,
    static_assets_present,
    static_assets_root,
)
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.main._create_dev_app import create_dev_app
from streambuild.dev_server.models import CompileOutcome


def run_dev_server(
    *,
    run_compile: Callable[[], CompileAnalysis],
    connection: AdapterConnection | None,
    database: str | None,
    host: str,
    port: int,
) -> int:
    """Compile once, serve the API and packaged UI, and block until shutdown."""

    assets_root: Path = static_assets_root()
    if not static_assets_present(assets_root=assets_root):
        print(
            "stb dev: built UI not found at "
            f"{assets_root}; run `make ui-build` to build and package it.",
            file=sys.stderr,
        )
        return 1
    state: DevServerState = DevServerState(run_compile=run_compile)
    outcome: CompileOutcome = state.current()
    app: FastAPI = create_dev_app(state=state, connection=connection, database=database)
    app = register_static_assets(app=app, assets_root=assets_root)
    print(f"StreamBuild dev server: http://{host}:{port} (compile: {outcome.state})")
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0
