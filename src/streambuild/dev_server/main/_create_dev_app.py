"""Build the dev server FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.dev_server._helpers.api_routes import register_api_routes
from streambuild.dev_server.classes.build_process import BuildProcessManager
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.kafka_lag_reader import KafkaLagReader
from streambuild.dev_server.classes.silent_reporter import SilentDevServerReporter
from streambuild.dev_server.exceptions import DevConfigurationError
from streambuild.dev_server.models import DevExecutionContext
from streambuild.dev_server.types import DevServerReporter


def create_dev_app(
    *,
    state: DevServerState,
    connection: AdapterConnection | None = None,
    database: str | None = None,
    project_dir: Path | None = None,
    reporter: DevServerReporter | None = None,
    execution_context: DevExecutionContext | None = None,
) -> FastAPI:
    """Assemble one application over the shared long-running server state."""

    active_reporter: DevServerReporter = reporter or SilentDevServerReporter()
    active_context: DevExecutionContext = execution_context or DevExecutionContext(
        database=database
    )
    if database is not None and active_context.database not in {None, database}:
        raise DevConfigurationError(
            "Dev server database does not match its retained execution context: "
            f"'{database}' != '{active_context.database}'"
        )
    if active_context.database is None:
        active_context = replace(active_context, database=database)
    effective_database: str | None = active_context.database
    builds: BuildProcessManager = BuildProcessManager(
        reporter=active_reporter, execution_context=active_context
    )
    kafka_lag_reader: KafkaLagReader = KafkaLagReader()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        kafka_lag_reader.close()
        builds.close()

    app: FastAPI = FastAPI(title="StreamBuild", docs_url=None, redoc_url=None, lifespan=lifespan)
    return register_api_routes(
        app=app,
        state=state,
        connection=connection,
        database=effective_database,
        project_dir=project_dir or Path.cwd(),
        builds=builds,
        kafka_lag_reader=kafka_lag_reader,
        execution_context=active_context,
        reporter=active_reporter,
    )
