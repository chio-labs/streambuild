"""Sensor listing, tick history, dead-letter, and override routes."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.auth.main.read_authenticated_request import read_authenticated_request
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.payloads.sensors_payload import (
    build_dead_letters_payload,
    build_sensor_ticks_payload,
    build_sensors_payload,
)
from streambuild.dev_server._helpers.server.authorization_enforcement import (
    require_automation_authorization,
)
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.sensor_scheduler import SensorScheduler
from streambuild.dev_server.models import (
    OperationAuthorizationContext,
    SensorDeadLetterActionRequest,
    SensorStatusRequest,
)
from streambuild.sensors.classes.sensor_dispatcher import SensorDispatcher
from streambuild.sensors.classes.sensor_state_repository import SensorStateRepository
from streambuild.sensors.exceptions import SensorError
from streambuild.sensors.models import SensorRegistry
from streambuild.sensors.types import SensorOverrideStatus, SensorTickStatus

_HTTP_BAD_REQUEST: int = 400
_HTTP_NOT_FOUND: int = 404
_HTTP_BAD_GATEWAY: int = 502
_HTTP_SERVICE_UNAVAILABLE: int = 503


def register_sensor_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    database: str | None,
    sensor_scheduler: SensorScheduler,
    authorization: OperationAuthorizationContext,
    read_connection: Callable[[], AbstractContextManager[AdapterConnection]],
    servable_analysis: Callable[[], CompileAnalysis],
) -> FastAPI:
    """Attach the sensor observability and management routes."""

    def _required_repository() -> SensorStateRepository:
        repository: SensorStateRepository | None = sensor_scheduler.repository
        if repository is None:
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE,
                detail="no warehouse connection",
            )
        return repository

    def _registry(*, analysis: CompileAnalysis) -> SensorRegistry:
        if analysis.sensors is None:
            return SensorRegistry()
        return analysis.sensors.registry

    @contextmanager
    def _read_repository(*, analysis: CompileAnalysis) -> Iterator[SensorStateRepository | None]:
        if database is None or not _registry(analysis=analysis).sensors:
            yield None
            return
        with read_connection() as connection:
            yield SensorStateRepository(connection=connection, database=database)

    def _require_sensor(*, analysis: CompileAnalysis, sensor_name: str) -> None:
        if sensor_name not in _registry(analysis=analysis).sensors:
            raise HTTPException(
                status_code=_HTTP_NOT_FOUND,
                detail=f"Unknown sensor '{sensor_name}'",
            )

    def read_sensors() -> dict[str, object]:
        analysis: CompileAnalysis = servable_analysis()
        try:
            with _read_repository(analysis=analysis) as repository:
                return build_sensors_payload(
                    analysis=analysis,
                    repository=repository,
                    health=sensor_scheduler.health(),
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def _window_bound(*, name: str, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            _ = datetime.fromisoformat(value)
        except ValueError as error:
            raise HTTPException(
                status_code=_HTTP_BAD_REQUEST,
                detail=f"{name} must be an ISO timestamp, received '{value}'",
            ) from error
        return value

    def read_sensor_ticks(
        *,
        sensor_name: str,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        after: Annotated[str | None, Query()] = None,
        before: Annotated[str | None, Query()] = None,
    ) -> dict[str, object]:
        analysis: CompileAnalysis = servable_analysis()
        _require_sensor(analysis=analysis, sensor_name=sensor_name)
        try:
            with _read_repository(analysis=analysis) as repository:
                return build_sensor_ticks_payload(
                    repository=repository,
                    sensor_name=sensor_name,
                    limit=limit,
                    after=_window_bound(name="after", value=after),
                    before=_window_bound(name="before", value=before),
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_dead_letters() -> dict[str, object]:
        analysis: CompileAnalysis = servable_analysis()
        try:
            with _read_repository(analysis=analysis) as repository:
                return build_dead_letters_payload(repository=repository)
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    app.get("/api/sensors")(read_sensors)
    app.get("/api/sensors/dead-letters")(read_dead_letters)
    app.get("/api/sensors/{sensor_name}/ticks")(read_sensor_ticks)
    return _register_sensor_action_routes(
        app=app,
        state=state,
        database=database,
        sensor_scheduler=sensor_scheduler,
        authorization=authorization,
        isolated_connection=read_connection,
        servable_analysis=servable_analysis,
    )


def _register_sensor_action_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    database: str | None,
    sensor_scheduler: SensorScheduler,
    authorization: OperationAuthorizationContext,
    isolated_connection: Callable[[], AbstractContextManager[AdapterConnection]],
    servable_analysis: Callable[[], CompileAnalysis],
) -> FastAPI:
    """Attach the sensor override and dead-letter action routes."""

    def _required_repository() -> SensorStateRepository:
        repository: SensorStateRepository | None = sensor_scheduler.repository
        if repository is None:
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE,
                detail="no warehouse connection",
            )
        return repository

    def _registry(*, analysis: CompileAnalysis) -> SensorRegistry:
        if analysis.sensors is None:
            return SensorRegistry()
        return analysis.sensors.registry

    @contextmanager
    def _override_repository() -> Iterator[SensorStateRepository]:
        _ = _required_repository()
        if database is None:
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE,
                detail="no warehouse connection",
            )
        with isolated_connection() as connection:
            yield SensorStateRepository(connection=connection, database=database)

    def _require_sensor(*, analysis: CompileAnalysis, sensor_name: str) -> None:
        if sensor_name not in _registry(analysis=analysis).sensors:
            raise HTTPException(
                status_code=_HTTP_NOT_FOUND,
                detail=f"Unknown sensor '{sensor_name}'",
            )

    def set_sensor_status(
        *, http_request: Request, sensor_name: str, request: SensorStatusRequest
    ) -> dict[str, object]:
        analysis: CompileAnalysis = servable_analysis()
        _require_sensor(analysis=analysis, sensor_name=sensor_name)
        try:
            status: SensorOverrideStatus = SensorOverrideStatus(request.status)
        except ValueError as error:
            raise HTTPException(
                status_code=_HTTP_BAD_REQUEST,
                detail=f"Unknown sensor status '{request.status}'",
            ) from error
        require_automation_authorization(
            analysis=analysis, request=http_request, context=authorization
        )
        try:
            with _override_repository() as repository:
                repository.ensure_ready()
                repository.record_override(
                    sensor_name=sensor_name,
                    status=status,
                    actor=read_authenticated_request(request=http_request).principal.username,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        return {"sensorName": sensor_name, "status": str(status)}

    def retry_dead_letter(
        *, http_request: Request, request: SensorDeadLetterActionRequest
    ) -> dict[str, object]:
        analysis: CompileAnalysis = servable_analysis()
        _require_sensor(analysis=analysis, sensor_name=request.sensorName)
        require_automation_authorization(
            analysis=analysis, request=http_request, context=authorization
        )
        dispatcher: SensorDispatcher | None = sensor_scheduler.build_dispatcher(analysis=analysis)
        if dispatcher is None:
            _ = _required_repository()
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE, detail="no warehouse connection"
            )
        try:
            with state.query_lock:
                status: SensorTickStatus = dispatcher.retry_dead_letter(
                    registry=_registry(analysis=analysis),
                    sensor_name=request.sensorName,
                    event_id=request.eventId,
                )
        except SensorError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        return {
            "sensorName": request.sensorName,
            "eventId": request.eventId,
            "status": str(status),
        }

    def skip_dead_letter(
        *, http_request: Request, request: SensorDeadLetterActionRequest
    ) -> dict[str, object]:
        analysis: CompileAnalysis = servable_analysis()
        _require_sensor(analysis=analysis, sensor_name=request.sensorName)
        reason: str = (request.reason or "").strip()
        if not reason:
            raise HTTPException(
                status_code=_HTTP_BAD_REQUEST,
                detail="Skipping a dead letter requires a reason",
            )
        require_automation_authorization(
            analysis=analysis, request=http_request, context=authorization
        )
        dispatcher: SensorDispatcher | None = sensor_scheduler.build_dispatcher(analysis=analysis)
        if dispatcher is None:
            _ = _required_repository()
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE, detail="no warehouse connection"
            )
        try:
            with state.query_lock:
                dispatcher.skip_dead_letter(
                    registry=_registry(analysis=analysis),
                    sensor_name=request.sensorName,
                    event_id=request.eventId,
                    reason=reason,
                )
        except SensorError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        return {
            "sensorName": request.sensorName,
            "eventId": request.eventId,
            "status": str(SensorTickStatus.SKIPPED),
        }

    app.post("/api/sensors/{sensor_name}/status")(set_sensor_status)
    app.post("/api/sensors/dead-letters/retry")(retry_dead_letter)
    app.post("/api/sensors/dead-letters/skip")(skip_dead_letter)
    return app
