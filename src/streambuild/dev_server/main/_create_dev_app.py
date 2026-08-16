"""Build the dev server FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.auth.classes.authentication_service import AuthenticationService
from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.main.register_authentication_routes import register_authentication_routes
from streambuild.auth.models import AuthSettings
from streambuild.dev_server._helpers.server.api_routes import register_api_routes
from streambuild.dev_server._helpers.server.authentication_runtime import (
    build_authentication_runtime,
)
from streambuild.dev_server._helpers.server.runtime_services import (
    build_dev_app_lifespan,
    build_runtime_services,
)
from streambuild.dev_server.classes.audit_scheduler import AuditScheduler
from streambuild.dev_server.classes.build_process import BuildProcessManager
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.kafka_lag_reader import KafkaLagReader
from streambuild.dev_server.classes.kafka_topic_reader import KafkaTopicReader
from streambuild.dev_server.classes.sensor_scheduler import SensorScheduler
from streambuild.dev_server.classes.silent_reporter import SilentDevServerReporter
from streambuild.dev_server.exceptions import DevConfigurationError
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
    auth_settings: AuthSettings | None = None,
    control_store: ControlStore | None = None,
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
    effective_project_dir: Path = project_dir or Path.cwd()
    authentication_runtime: tuple[AuthenticationService, ControlStore, bool] = (
        build_authentication_runtime(
            project_dir=effective_project_dir,
            auth_settings=auth_settings,
            control_store=control_store,
        )
    )
    authentication: AuthenticationService = authentication_runtime[0]
    active_control_store: ControlStore = authentication_runtime[1]
    owns_control_store: bool = authentication_runtime[2]
    if connection is not None and effective_database is not None:
        connection.validate_metadata_state(effective_database)
    runtime_services: tuple[
        BuildProcessManager, KafkaLagReader, KafkaTopicReader, AuditScheduler, SensorScheduler
    ] = build_runtime_services(
        state=state,
        connection=connection,
        observation_connection=observation_connection,
        database=effective_database,
        project_dir=effective_project_dir,
        reporter=active_reporter,
        execution_context=active_context,
    )
    builds: BuildProcessManager = runtime_services[0]
    kafka_lag_reader: KafkaLagReader = runtime_services[1]
    kafka_topic_reader: KafkaTopicReader = runtime_services[2]
    audit_scheduler: AuditScheduler = runtime_services[3]
    sensor_scheduler: SensorScheduler = runtime_services[4]

    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] = build_dev_app_lifespan(
        state=state,
        database=effective_database,
        builds=builds,
        kafka_lag_reader=kafka_lag_reader,
        kafka_topic_reader=kafka_topic_reader,
        audit_scheduler=audit_scheduler,
        sensor_scheduler=sensor_scheduler,
        control_store=active_control_store,
        owns_control_store=owns_control_store,
    )
    app: FastAPI = FastAPI(title="StreamBuild", docs_url=None, redoc_url=None, lifespan=lifespan)
    app = register_authentication_routes(app=app, service=authentication)
    return register_api_routes(
        app=app,
        state=state,
        connection=connection,
        project_dir=effective_project_dir,
        builds=builds,
        schedulers=(audit_scheduler, sensor_scheduler),
        broker_readers=(kafka_lag_reader, kafka_topic_reader),
        execution_context=active_context,
        reporter=active_reporter,
        control_store=active_control_store,
    )
