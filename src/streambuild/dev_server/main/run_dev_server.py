"""Start the long-running dev server over one compiled project."""

from __future__ import annotations

import ipaddress
import sys
from collections.abc import Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.auth.constants import LOCALHOST_NAME
from streambuild.auth.main.default_control_store_url import default_control_store_url
from streambuild.auth.models import AuthSettings
from streambuild.auth.types import AuthenticationMode
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.server.static_assets import (
    register_static_assets,
    static_assets_present,
    static_assets_root,
)
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.main._create_dev_app import create_dev_app
from streambuild.dev_server.models import CompileOutcome, DevExecutionContext
from streambuild.dev_server.types import DevServerReporter


def run_dev_server(
    *,
    run_compile: Callable[[], CompileAnalysis],
    connection: AdapterConnection | None,
    observation_connection: AdapterConnection | None,
    database: str | None,
    project_dir: Path,
    host: str,
    port: int,
    reporter: DevServerReporter,
    execution_context: DevExecutionContext | None = None,
    auth_settings: AuthSettings | None = None,
) -> int:
    """Compile once, serve the API and packaged UI, and block until shutdown."""

    effective_auth_settings: AuthSettings = auth_settings or AuthSettings(
        mode=AuthenticationMode.DISABLED,
        control_store_url=default_control_store_url(project_dir=project_dir),
    )
    if effective_auth_settings.mode == AuthenticationMode.DISABLED and not _is_loopback_bind(host):
        print(
            "stb dev: disabled authentication may only bind to a loopback address; "
            "configure --auth-mode for shared access.",
            file=sys.stderr,
        )
        return 1
    if (
        effective_auth_settings.mode == AuthenticationMode.PASSWORD
        and not effective_auth_settings.session_cookie_secure
        and not _is_loopback_bind(host)
    ):
        print(
            "stb dev: insecure password cookies may only be used on a loopback address.",
            file=sys.stderr,
        )
        return 1
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
    app: FastAPI = create_dev_app(
        state=state,
        connection=connection,
        observation_connection=observation_connection,
        database=database,
        project_dir=project_dir,
        reporter=reporter,
        execution_context=execution_context,
        auth_settings=effective_auth_settings,
    )
    app = register_static_assets(app=app, assets_root=assets_root)
    reporter.report_startup(
        outcome=outcome, project_dir=project_dir, database=database, host=host, port=port
    )
    uvicorn.run(app, host=host, port=port, log_level="warning")
    reporter.report_shutdown()
    return 0


def _is_loopback_bind(host: str) -> bool:
    if host == LOCALHOST_NAME:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
