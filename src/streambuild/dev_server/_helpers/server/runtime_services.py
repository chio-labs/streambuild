"""Construct the cooperating runtime services and their application lifecycle."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from streambuild.auth.classes.control_store import ControlStore
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.payloads.state_payload import build_topics_payload
from streambuild.dev_server.classes.audit_scheduler import AuditScheduler
from streambuild.dev_server.classes.build_process import BuildProcessManager
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.kafka_lag_reader import KafkaLagReader
from streambuild.dev_server.classes.kafka_topic_reader import KafkaTopicReader
from streambuild.dev_server.classes.sensor_scheduler import SensorScheduler
from streambuild.dev_server.classes.warehouse_runtime import WarehouseRuntime
from streambuild.dev_server.exceptions import ProjectNotCompiledError
from streambuild.dev_server.models import DevExecutionContext
from streambuild.dev_server.types import DevServerReporter


def build_runtime_services(
    *,
    state: DevServerState,
    warehouse: WarehouseRuntime,
    database: str | None,
    project_dir: Path,
    reporter: DevServerReporter,
    execution_context: DevExecutionContext,
) -> tuple[BuildProcessManager, KafkaLagReader, KafkaTopicReader, AuditScheduler, SensorScheduler]:
    """Build process, broker, audit, and sensor runtime services as one bundle."""

    builds: BuildProcessManager = BuildProcessManager(
        reporter=reporter, execution_context=execution_context
    )
    kafka_lag_reader: KafkaLagReader = KafkaLagReader()
    kafka_topic_reader: KafkaTopicReader = KafkaTopicReader()
    audit_scheduler: AuditScheduler = AuditScheduler(
        state=state,
        warehouse=warehouse,
        database=database,
        project_dir=project_dir,
        builds=builds,
        presumed_failed_after_seconds=execution_context.run_presumed_failed_after_seconds,
    )
    sensor_scheduler: SensorScheduler = SensorScheduler(
        state=state,
        warehouse=warehouse,
        database=database,
    )
    return builds, kafka_lag_reader, kafka_topic_reader, audit_scheduler, sensor_scheduler


def build_dev_app_lifespan(
    *,
    state: DevServerState,
    database: str | None,
    builds: BuildProcessManager,
    kafka_lag_reader: KafkaLagReader,
    kafka_topic_reader: KafkaTopicReader,
    audit_scheduler: AuditScheduler,
    sensor_scheduler: SensorScheduler,
    control_store: ControlStore,
    owns_control_store: bool,
    warehouse: WarehouseRuntime,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Start schedulers and warm caches on startup; close everything on shutdown."""

    def _warm_broker_caches() -> None:
        try:
            analysis: CompileAnalysis = state.current_analysis()
        except ProjectNotCompiledError:
            return
        _ = build_topics_payload(
            analysis=analysis,
            connection=None,
            database=database,
            topic_reader=kafka_topic_reader,
            kafka_lag_reader=kafka_lag_reader,
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        warehouse.start()
        audit_scheduler.start()
        sensor_scheduler.start()
        _warm_broker_caches()
        yield
        sensor_scheduler.close()
        audit_scheduler.close()
        kafka_lag_reader.close()
        kafka_topic_reader.close()
        builds.close()
        warehouse.close()
        if owns_control_store:
            control_store.close()

    return lifespan
