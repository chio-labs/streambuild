"""Register the JSON API routes on one FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.cli.build.main.prepare_build_workflow import prepare_build_workflow
from streambuild.cli.build.main.validate_build_pipeline_limit import validate_build_pipeline_limit
from streambuild.cli.build.models import (
    DirectWorkflowPreparation,
    MixedWorkflowPreparation,
    VirtualWorkflowPreparation,
    WorkflowPreparationOptions,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.compiler.compile.models import CompiledSource
from streambuild.compiler.discovery.models import KafkaLandingStep
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.dev_server._helpers.payloads.definitions_payload import build_definitions_payload
from streambuild.dev_server._helpers.payloads.deployments_payload import (
    build_deployment_detail_payload,
    build_deployments_payload,
)
from streambuild.dev_server._helpers.payloads.plan_payload import (
    build_mode_aware_plan_payload,
    count_replay_rows,
)
from streambuild.dev_server._helpers.payloads.state_payload import (
    build_state_payload,
    build_topics_payload,
)
from streambuild.dev_server._helpers.queries.message_query import (
    ensure_header_columns,
    read_source_message_facets,
    read_source_message_record,
    read_source_messages,
)
from streambuild.dev_server._helpers.queries.runs_query import (
    read_active_runs,
    read_run_events,
    read_runs,
)
from streambuild.dev_server._helpers.server.checks_execution import (
    build_checks_status_payload,
    run_one_audit,
    run_one_test,
)
from streambuild.dev_server._helpers.server.compile_runner import build_status_payload
from streambuild.dev_server._helpers.server.deployment_operations import (
    build_deployment_diff_payload,
    run_deployment_cleanup,
    run_deployment_promotion,
)
from streambuild.dev_server.classes.audit_scheduler import AuditScheduler
from streambuild.dev_server.classes.build_process import BuildProcessManager, build_invocation
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.kafka_lag_reader import KafkaLagReader
from streambuild.dev_server.classes.kafka_topic_reader import KafkaTopicReader
from streambuild.dev_server.exceptions import (
    BuildInProgressError,
    BuildStartError,
    DevServerError,
    MessageQueryValidationError,
    MessageSchemaError,
    ProjectNotCompiledError,
)
from streambuild.dev_server.main._build_audit_scheduler_payload import (
    build_audit_scheduler_payload,
)
from streambuild.dev_server.models import (
    BuildRunRequest,
    ChecksRunRequest,
    CompileOutcome,
    DeploymentCleanupRequest,
    DevExecutionContext,
    MessageFacetsRequest,
    MessageRecordRequest,
    MessagesQueryRequest,
)
from streambuild.dev_server.types import (
    ActivityTone,
    AuditScheduleState,
    DevServerReporter,
    RunPresentationStatus,
)
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.direct.exceptions import DirectBuildError
from streambuild.executor.observability.main.logical_resource_identities import (
    logical_resource_identities,
)

_HTTP_BAD_REQUEST: int = 400
_HTTP_NOT_FOUND: int = 404
_HTTP_CONFLICT: int = 409
_HTTP_BAD_GATEWAY: int = 502
_HTTP_SERVICE_UNAVAILABLE: int = 503


def register_api_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    connection: AdapterConnection | None,
    project_dir: Path,
    builds: BuildProcessManager,
    audit_scheduler: AuditScheduler,
    kafka_lag_reader: KafkaLagReader,
    kafka_topic_reader: KafkaTopicReader,
    reporter: DevServerReporter,
    execution_context: DevExecutionContext,
) -> FastAPI:
    """Attach every /api route; handlers close over the shared server state."""

    database: str | None = execution_context.database

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
        reporter.report_reload(outcome=outcome)
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

    def read_state() -> dict[str, object]:
        if connection is None or database is None:
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE,
                detail="no warehouse connection",
            )
        try:
            analysis: CompileAnalysis = state.current_analysis()
        except ProjectNotCompiledError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        try:
            with state.query_lock:
                return build_state_payload(
                    analysis=analysis,
                    connection=connection,
                    database=database,
                    kafka_lag_reader=kafka_lag_reader,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def _required_connection() -> AdapterConnection:
        if connection is None or database is None:
            raise HTTPException(
                status_code=_HTTP_SERVICE_UNAVAILABLE,
                detail="no warehouse connection",
            )
        return connection

    def _servable_analysis() -> CompileAnalysis:
        try:
            return state.current_analysis()
        except ProjectNotCompiledError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error

    def read_plan(
        *,
        select: Annotated[list[str] | None, Query()] = None,
        start: Annotated[str | None, Query()] = None,
        deployment: Annotated[str | None, Query()] = None,
    ) -> dict[str, object]:
        client: AdapterConnection = _required_connection()
        analysis: CompileAnalysis = _servable_analysis()
        try:
            if start is not None and not select:
                raise CliUserError("--start-time requires at least one --select")
            with state.query_lock:
                planned_at: str = client.capture_warehouse_timestamp()
                preparation: (
                    DirectWorkflowPreparation
                    | MixedWorkflowPreparation
                    | VirtualWorkflowPreparation
                ) = prepare_build_workflow(
                    analysis=analysis,
                    options=WorkflowPreparationOptions(
                        database=database,
                        metadata_database=database,
                        selectors=tuple(select or ()),
                        deployment_id=deployment,
                        full_refresh=False,
                        start_time=start,
                        verbose=False,
                    ),
                    client=client,
                    adapter_profile=analysis.adapter_profile,
                )
                direct: DirectWorkflowPreparation | None = _direct_preparation(preparation)
                resolved_deployment_id: str | None = _resolved_deployment_id(preparation)
                _, command = build_invocation(
                    selectors=tuple(select or ()),
                    start_time=start,
                    deployment_id=resolved_deployment_id,
                    execution_context=execution_context,
                )
                replay_row_counts: dict[str, int | None] = (
                    {}
                    if direct is None
                    else count_replay_rows(
                        connection=client,
                        database=direct.preview.database,
                        plan=direct.preview.plan,
                        start_time=direct.preview.effective_start_time,
                    )
                )
                return build_mode_aware_plan_payload(
                    preparation=preparation,
                    analysis=analysis,
                    selectors=tuple(select or ()),
                    planned_at=planned_at,
                    command=command,
                    replay_row_counts=replay_row_counts,
                )
        except (
            BackfillExecutionError,
            CliUserError,
            DirectBuildError,
            DirectPlanError,
            ValueError,
        ) as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_topics() -> dict[str, object]:
        analysis: CompileAnalysis = _servable_analysis()
        try:
            with state.query_lock:
                return build_topics_payload(
                    analysis=analysis,
                    connection=connection,
                    database=database,
                    topic_reader=kafka_topic_reader,
                    kafka_lag_reader=kafka_lag_reader,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    app.get("/api/status")(read_status)
    app.get("/api/state")(read_state)
    app.get("/api/plan")(read_plan)
    app.post("/api/reload")(reload_project)
    app.get("/api/definitions")(read_definitions)
    app.get("/api/topics")(read_topics)
    _register_deployment_routes(
        app=app,
        state=state,
        database=database,
        project_dir=project_dir,
        required_connection=_required_connection,
    )
    _register_message_routes(
        app=app,
        state=state,
        database=database,
        required_connection=_required_connection,
        servable_analysis=_servable_analysis,
    )
    return _register_quality_routes(
        app=app,
        state=state,
        database=database,
        project_dir=project_dir,
        builds=builds,
        audit_scheduler=audit_scheduler,
        reporter=reporter,
        required_connection=_required_connection,
        servable_analysis=_servable_analysis,
        presumed_failed_after_seconds=execution_context.run_presumed_failed_after_seconds,
    )


def _register_deployment_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    database: str | None,
    project_dir: Path,
    required_connection: Callable[[], AdapterConnection],
) -> FastAPI:
    """Attach the deployment inventory, detail and lifecycle routes."""

    def read_deployments() -> dict[str, object]:
        client: AdapterConnection = required_connection()
        try:
            with state.query_lock:
                return build_deployments_payload(
                    connection=client,
                    database=database or "",
                    metadata_database=database or "",
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_one_deployment(*, deployment_id: str) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        try:
            with state.query_lock:
                payload: dict[str, object] | None = build_deployment_detail_payload(
                    connection=client,
                    database=database or "",
                    metadata_database=database or "",
                    deployment_id=deployment_id,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        if payload is None:
            raise HTTPException(
                status_code=_HTTP_NOT_FOUND,
                detail=f"deployment '{deployment_id}' was not found",
            )
        return payload

    def read_deployment_diff(
        *, deployment_id: str, against: Annotated[str | None, Query()] = None
    ) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        comparison: str = deployment_id if against is None else f"{against}:{deployment_id}"
        try:
            with state.query_lock:
                return build_deployment_diff_payload(
                    connection=client,
                    database=database or "",
                    metadata_database=database or "",
                    comparison=comparison,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error

    def promote_deployment(*, deployment_id: str) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        try:
            with state.query_lock:
                return run_deployment_promotion(
                    connection=client,
                    database=database or "",
                    metadata_database=database or "",
                    deployment_id=deployment_id,
                    project_dir=project_dir,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error

    def cleanup_deployments(request: DeploymentCleanupRequest) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        try:
            with state.query_lock:
                return run_deployment_cleanup(
                    connection=client,
                    database=database or "",
                    metadata_database=database or "",
                    retention_days=request.retentionDays,
                    project_dir=project_dir,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error

    app.get("/api/deployments")(read_deployments)
    app.get("/api/deployments/{deployment_id}")(read_one_deployment)
    app.get("/api/deployments/{deployment_id}/diff")(read_deployment_diff)
    app.post("/api/deployments/{deployment_id}/promote")(promote_deployment)
    app.post("/api/deployments/cleanup")(cleanup_deployments)
    return app


def _register_message_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    database: str | None,
    required_connection: Callable[[], AdapterConnection],
    servable_analysis: Callable[[], CompileAnalysis],
) -> FastAPI:
    """Attach the warehouse-backed source message browsing routes."""

    def _browsable_relation_name(*, analysis: CompileAnalysis, source_name: str) -> str:
        source: CompiledSource | None = next(
            (
                candidate
                for candidate in analysis.compiled_project.sources
                if candidate.key.name == source_name
            ),
            None,
        )
        if source is None:
            raise HTTPException(
                status_code=_HTTP_NOT_FOUND,
                detail=f"unknown source '{source_name}'",
            )
        if not isinstance(source.source, KafkaLandingStep):
            raise HTTPException(
                status_code=_HTTP_BAD_REQUEST,
                detail=f"source '{source_name}' is not a managed Kafka source",
            )
        return analysis.realized_project.relation_name_by_logical_key[source.key]

    def read_messages(*, name: str, request: MessagesQueryRequest) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        analysis: CompileAnalysis = servable_analysis()
        relation_name: str = _browsable_relation_name(analysis=analysis, source_name=name)
        try:
            with state.query_lock:
                ensure_header_columns(
                    connection=client, database=database or "", relation_name=relation_name
                )
                return read_source_messages(
                    connection=client,
                    database=database or "",
                    relation_name=relation_name,
                    request=request,
                )
        except MessageQueryValidationError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except MessageSchemaError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_message_record(*, name: str, request: MessageRecordRequest) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        analysis: CompileAnalysis = servable_analysis()
        relation_name: str = _browsable_relation_name(analysis=analysis, source_name=name)
        try:
            with state.query_lock:
                ensure_header_columns(
                    connection=client, database=database or "", relation_name=relation_name
                )
                record: dict[str, object] | None = read_source_message_record(
                    connection=client,
                    database=database or "",
                    relation_name=relation_name,
                    partition=request.partition,
                    offset=request.offset,
                )
        except MessageQueryValidationError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except MessageSchemaError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        if record is None:
            raise HTTPException(
                status_code=_HTTP_NOT_FOUND,
                detail=(
                    f"no message at partition {request.partition} "
                    f"offset {request.offset} in '{name}'"
                ),
            )
        return record

    def read_message_facets(*, name: str, request: MessageFacetsRequest) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        analysis: CompileAnalysis = servable_analysis()
        relation_name: str = _browsable_relation_name(analysis=analysis, source_name=name)
        try:
            with state.query_lock:
                ensure_header_columns(
                    connection=client, database=database or "", relation_name=relation_name
                )
                return read_source_message_facets(
                    connection=client,
                    database=database or "",
                    relation_name=relation_name,
                    request=request,
                )
        except MessageQueryValidationError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except MessageSchemaError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    app.post("/api/sources/{name}/messages")(read_messages)
    app.post("/api/sources/{name}/messages/record")(read_message_record)
    app.post("/api/sources/{name}/messages/facets")(read_message_facets)
    return app


def _register_quality_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    database: str | None,
    project_dir: Path,
    builds: BuildProcessManager,
    audit_scheduler: AuditScheduler,
    reporter: DevServerReporter,
    required_connection: Callable[[], AdapterConnection],
    servable_analysis: Callable[[], CompileAnalysis],
    presumed_failed_after_seconds: int,
) -> FastAPI:
    """Attach the checks, run-history, and build routes."""

    def run_check(request: ChecksRunRequest) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        analysis: CompileAnalysis = servable_analysis()
        runners: dict[str, Callable[..., dict[str, object]]] = {
            "audit": run_one_audit,
            "test": run_one_test,
        }
        runner: Callable[..., dict[str, object]] | None = runners.get(request.kind)
        if runner is None:
            raise HTTPException(
                status_code=_HTTP_BAD_REQUEST,
                detail="kind must be 'audit' or 'test'",
            )
        try:
            with state.query_lock:
                payload: dict[str, object] = runner(
                    analysis=analysis,
                    connection=client,
                    name=request.name,
                    project_dir=project_dir,
                    database=database or "",
                )
        except DevServerError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        deferred: bool = payload.get("deferredUntil") is not None
        passed: bool = bool(payload.get("passed"))
        reporter.report_activity(
            category=request.kind,
            status="deferred" if deferred else ("pass" if passed else "fail"),
            tone=(
                ActivityTone.CAUTION
                if deferred
                else (ActivityTone.GOOD if passed else ActivityTone.BAD)
            ),
            detail=request.name,
        )
        return payload

    def read_checks_status() -> list[dict[str, object]]:
        client: AdapterConnection = required_connection()
        analysis: CompileAnalysis = servable_analysis()
        try:
            with state.query_lock:
                return build_checks_status_payload(
                    analysis=analysis,
                    connection=client,
                    database=database or "",
                    project_dir=project_dir,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_audit_scheduler() -> dict[str, object]:
        client: AdapterConnection = required_connection()
        health: dict[str, object] = audit_scheduler.health()
        if health["state"] in {
            AuditScheduleState.RUNNING,
            AuditScheduleState.BACKING_OFF,
        }:
            return {
                "enabled": True,
                "state": health["state"],
                "warehouseNow": health["lastSuccessfulTick"],
                "dueCount": health["runningAuditCount"],
                "audits": [],
                "health": health,
            }
        analysis: CompileAnalysis = servable_analysis()
        try:
            with state.query_lock:
                payload: dict[str, object] = build_audit_scheduler_payload(
                    analysis=analysis,
                    connection=client,
                    database=database or "",
                    project_dir=project_dir,
                )
                payload["health"] = health
                return payload
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_run_history() -> list[dict[str, object]]:
        client: AdapterConnection = required_connection()
        try:
            with state.query_lock:
                return read_runs(
                    connection=client,
                    database=database or "",
                    presumed_failed_after_seconds=presumed_failed_after_seconds,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_one_run_events(
        *, invocation_id: str, after: Annotated[int, Query(ge=0)] = 0
    ) -> dict[str, object]:
        client: AdapterConnection = required_connection()
        try:
            with state.query_lock:
                return read_run_events(
                    connection=client,
                    database=database or "",
                    invocation_id=invocation_id,
                    after=after,
                    presumed_failed_after_seconds=presumed_failed_after_seconds,
                )
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    app.post("/api/checks/run")(run_check)
    app.get("/api/checks/status")(read_checks_status)
    app.get("/api/audit-scheduler")(read_audit_scheduler)
    app.get("/api/runs")(read_run_history)
    app.get("/api/runs/{invocation_id}/events")(read_one_run_events)
    return _register_build_routes(
        app=app,
        builds=builds,
        project_dir=project_dir,
        required_connection=required_connection,
        database=database or "",
        state=state,
        servable_analysis=servable_analysis,
        presumed_failed_after_seconds=presumed_failed_after_seconds,
    )


def _register_build_routes(
    *,
    app: FastAPI,
    builds: BuildProcessManager,
    project_dir: Path,
    required_connection: Callable[[], AdapterConnection],
    database: str,
    state: DevServerState,
    servable_analysis: Callable[[], CompileAnalysis],
    presumed_failed_after_seconds: int,
) -> FastAPI:
    """Attach the execute and live-feed routes."""

    def start_build(request: BuildRunRequest) -> dict[str, object]:
        try:
            with state.query_lock:
                client: AdapterConnection = required_connection()
                analysis: CompileAnalysis = servable_analysis()
                validate_build_pipeline_limit(
                    analysis=analysis,
                    selectors=tuple(request.selectors),
                )
                active_runs: list[dict[str, object]] = [
                    run
                    for run in read_active_runs(
                        connection=client,
                        database=database,
                        presumed_failed_after_seconds=presumed_failed_after_seconds,
                    )
                    if run["status"]
                    in {
                        RunPresentationStatus.RUNNING,
                        RunPresentationStatus.UNRESPONSIVE,
                    }
                ]
                blocking_run: dict[str, object] | None = None
                if active_runs:
                    preparation: (
                        DirectWorkflowPreparation
                        | MixedWorkflowPreparation
                        | VirtualWorkflowPreparation
                    ) = prepare_build_workflow(
                        analysis=analysis,
                        options=WorkflowPreparationOptions(
                            database=database,
                            metadata_database=database,
                            selectors=tuple(request.selectors),
                            deployment_id=request.deploymentId,
                            full_refresh=False,
                            start_time=request.startTime,
                            verbose=False,
                        ),
                        client=client,
                        adapter_profile=analysis.adapter_profile,
                    )
                    requested_writes, requested_reads = _preparation_logical_scopes(preparation)
                    blocking_run = next(
                        (
                            run
                            for run in active_runs
                            if _run_overlaps_requested_scope(
                                run=run,
                                requested_writes=requested_writes,
                                requested_reads=requested_reads,
                            )
                        ),
                        None,
                    )
                if blocking_run is not None:
                    raise BuildInProgressError(
                        _blocking_run_message(
                            run=blocking_run,
                            presumed_failed_after_seconds=presumed_failed_after_seconds,
                        )
                    )
                return builds.start(
                    project_dir=project_dir,
                    selectors=tuple(request.selectors),
                    start_time=request.startTime,
                    deployment_id=request.deploymentId,
                    confirmations=tuple(request.confirmations),
                )
        except BuildInProgressError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        except BuildStartError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except (
            BackfillExecutionError,
            CliUserError,
            DirectBuildError,
            DirectPlanError,
            ValueError,
        ) as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_build_feed(*, after: Annotated[int, Query(ge=0)] = 0) -> dict[str, object]:
        return builds.feed(after=after)

    def cancel_build(request: dict[str, str]) -> dict[str, object]:
        try:
            return builds.cancel(invocation_id=request.get("invocationId", ""))
        except BuildInProgressError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error

    def kill_build(request: dict[str, str]) -> dict[str, object]:
        try:
            return builds.kill(invocation_id=request.get("invocationId", ""))
        except BuildInProgressError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error

    app.post("/api/build")(start_build)
    app.get("/api/build/current")(read_build_feed)
    app.post("/api/build/cancel")(cancel_build)
    app.post("/api/build/kill")(kill_build)
    return app


def _blocking_run_message(*, run: dict[str, object], presumed_failed_after_seconds: int) -> str:
    invocation_id: object = run["invocationId"]
    status: object = run["status"]
    signal_age_seconds: int = int(str(run["lastSignalAgeSeconds"]))
    if status == RunPresentationStatus.UNRESPONSIVE:
        retry_seconds: int = max(presumed_failed_after_seconds - signal_age_seconds, 0)
        return (
            f"Run {invocation_id} is unresponsive: no signal for {signal_age_seconds}s. "
            "No new run was started. To prevent overlapping warehouse writes, StreamBuild "
            f"will wait {retry_seconds}s more before treating it as presumed failed "
            f"(configured safety window: {presumed_failed_after_seconds}s via "
            "defaults.run_presumed_failed_after). Retry after that."
        )
    return (
        f"Run {invocation_id} is still {status} (last signal {signal_age_seconds}s ago), "
        "so no new run was started. Wait for it to finish or cancel it from Runs."
    )


def _direct_preparation(
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
) -> DirectWorkflowPreparation | None:
    if isinstance(preparation, DirectWorkflowPreparation):
        return preparation
    if isinstance(preparation, MixedWorkflowPreparation):
        return preparation.direct
    return None


def _resolved_deployment_id(
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
) -> str | None:
    if isinstance(preparation, VirtualWorkflowPreparation):
        return preparation.preview.deployment_id
    if isinstance(preparation, MixedWorkflowPreparation):
        return preparation.virtual.preview.deployment_id
    return None


def _preparation_logical_scopes(
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
) -> tuple[frozenset[str], frozenset[str]]:
    writes: set[str] = set()
    reads: set[str] = set()
    direct: DirectWorkflowPreparation | None = _direct_preparation(preparation)
    if direct is not None:
        writes.update(logical_resource_identities(direct.preview.plan.execution_scope))
        reads.update(
            logical_resource_identities(
                tuple(item.key for item in direct.preview.plan.prerequisite_scope)
            )
        )
    virtual: VirtualWorkflowPreparation | None = (
        preparation.virtual
        if isinstance(preparation, MixedWorkflowPreparation)
        else preparation
        if isinstance(preparation, VirtualWorkflowPreparation)
        else None
    )
    if virtual is not None:
        writes.update(logical_resource_identities(virtual.preview.run_execution_scope))
        reads.update(logical_resource_identities(virtual.preview.run_context_scope))
    return frozenset(writes), frozenset(reads)


def _run_overlaps_requested_scope(
    *,
    run: dict[str, object],
    requested_writes: frozenset[str],
    requested_reads: frozenset[str],
) -> bool:
    """Conservatively detect read/write conflicts between two direct build plans."""

    active_writes: frozenset[str] | None = _logical_id_scope(run.get("executedLogicalIds"))
    active_reads: frozenset[str] | None = _logical_id_scope(run.get("contextLogicalIds"))
    if active_writes is None or active_reads is None:
        return True
    return bool(
        (active_writes & requested_writes)
        or (active_writes & requested_reads)
        or (active_reads & requested_writes)
    )


def _logical_id_scope(value: object) -> frozenset[str] | None:
    if not isinstance(value, list):
        return None
    scope: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            return None
        scope.add(item)
    return frozenset(scope)
