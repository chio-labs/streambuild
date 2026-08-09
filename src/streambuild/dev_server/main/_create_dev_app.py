"""Build the dev server FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.payloads.state_payload import build_topics_payload
from streambuild.dev_server._helpers.server.api_routes import register_api_routes
from streambuild.dev_server.classes.audit_scheduler import AuditScheduler
from streambuild.dev_server.classes.build_process import BuildProcessManager
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.kafka_lag_reader import KafkaLagReader
from streambuild.dev_server.classes.kafka_topic_reader import KafkaTopicReader
from streambuild.dev_server.classes.silent_reporter import SilentDevServerReporter
from streambuild.dev_server.exceptions import DevConfigurationError, ProjectNotCompiledError
from streambuild.dev_server.models import DevExecutionContext
from streambuild.dev_server.types import DevServerReporter


def create_dev_app(
    *,
    state: DevServerState,
    connection: AdapterConnection | None = None,
    observation_connection: AdapterConnection | None = None,
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
    if connection is not None and effective_database is not None:
        connection.validate_metadata_state(effective_database)
    builds: BuildProcessManager = BuildProcessManager(
        reporter=active_reporter, execution_context=active_context
    )
    kafka_lag_reader: KafkaLagReader = KafkaLagReader()
    kafka_topic_reader: KafkaTopicReader = KafkaTopicReader()
    audit_scheduler: AuditScheduler = AuditScheduler(
        state=state,
        connection=connection,
        observation_connection=observation_connection,
        database=effective_database,
        project_dir=project_dir or Path.cwd(),
        builds=builds,
        presumed_failed_after_seconds=active_context.run_presumed_failed_after_seconds,
    )

    def _warm_broker_caches() -> None:
        """Kick the non-blocking broker metadata refreshes before the first request."""

        try:
            analysis: CompileAnalysis = state.current_analysis()
        except ProjectNotCompiledError:
            return
        _ = build_topics_payload(
            analysis=analysis,
            connection=None,
            database=effective_database,
            topic_reader=kafka_topic_reader,
            kafka_lag_reader=kafka_lag_reader,
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        audit_scheduler.start()
        _warm_broker_caches()
        yield
        audit_scheduler.close()
        kafka_lag_reader.close()
        kafka_topic_reader.close()
        builds.close()

    app: FastAPI = FastAPI(title="StreamBuild", docs_url=None, redoc_url=None, lifespan=lifespan)
    return register_api_routes(
        app=app,
        state=state,
        connection=connection,
        project_dir=project_dir or Path.cwd(),
        builds=builds,
        audit_scheduler=audit_scheduler,
        kafka_lag_reader=kafka_lag_reader,
        kafka_topic_reader=kafka_topic_reader,
        execution_context=active_context,
        reporter=active_reporter,
    )
