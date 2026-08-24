"""Frozen-plan API for recorded pipeline destruction and target reset."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import (
    AdapterError,
    AdapterTargetMutationLockError,
)
from streambuild.auth.main.read_authenticated_request import read_authenticated_request
from streambuild.auth.models import AuthenticatedRequest
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.server.authorization_enforcement import (
    require_destruction_authorization,
)
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.warehouse_runtime import WarehouseRuntime
from streambuild.dev_server.models import (
    CompileOutcome,
    DestructionExecutionRequest,
    DestructionPlanRequest,
    OperationAuthorizationContext,
)
from streambuild.executor.destruction.exceptions import (
    DestructionChallengeError,
    DestructionDependencyError,
    DestructionDriftError,
    DestructionExternalDependencyError,
    DestructionPlanCorruptError,
    DestructionPlanExpiredError,
    DestructionPlanNotFoundError,
    DestructionPlanNotReviewedError,
    DestructionRecordingError,
    DestructionSelectionError,
)
from streambuild.executor.destruction.main.execute_destruction import execute_destruction
from streambuild.executor.destruction.main.plan_destruction import plan_destruction
from streambuild.executor.destruction.models import (
    DestructionExecutionResult,
    DestructionPlan,
    DestructionRequest,
)
from streambuild.executor.destruction.types import DestructionPlanStore

_HTTP_BAD_REQUEST: int = 400
_HTTP_NOT_FOUND: int = 404
_HTTP_CONFLICT: int = 409
_HTTP_GONE: int = 410
_HTTP_BAD_GATEWAY: int = 502
_HTTP_SERVICE_UNAVAILABLE: int = 503


def register_destruction_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    warehouse: WarehouseRuntime,
    database: str | None,
    project_dir: Path,
    authorization: OperationAuthorizationContext,
    servable_analysis: Callable[[], CompileAnalysis],
    store: DestructionPlanStore,
) -> FastAPI:
    """Register the durable, actor-bound single-use frozen-plan service."""

    _ = _register_destruction_plan_routes(
        app=app,
        state=state,
        warehouse=warehouse,
        database=database,
        authorization=authorization,
        servable_analysis=servable_analysis,
        store=store,
    )
    return _register_destruction_execution_route(
        app=app,
        state=state,
        warehouse=warehouse,
        database=database,
        project_dir=project_dir,
        authorization=authorization,
        servable_analysis=servable_analysis,
        store=store,
    )


def _register_destruction_plan_routes(
    *,
    app: FastAPI,
    state: DevServerState,
    warehouse: WarehouseRuntime,
    database: str | None,
    authorization: OperationAuthorizationContext,
    servable_analysis: Callable[[], CompileAnalysis],
    store: DestructionPlanStore,
) -> FastAPI:
    """Attach frozen-plan creation, inspection, and review routes."""

    def create_plan(*, http_request: Request, request: DestructionPlanRequest) -> dict[str, object]:
        actor: AuthenticatedRequest = _actor(http_request)
        analysis: CompileAnalysis = servable_analysis()
        target: str = analysis.compiled_project.target_name or authorization.selected_target or ""
        connection: AdapterConnection = _required_connection(warehouse=warehouse, database=database)
        requested_names: tuple[str, ...] = tuple(request.pipelineNames)
        included_names: tuple[str, ...] = tuple(request.includedDependentPipelineNames)
        require_destruction_authorization(
            analysis=analysis,
            request=http_request,
            context=authorization,
            operation=request.operation,
            affected_pipelines=requested_names,
        )
        try:
            with state.query_lock:
                plan: DestructionPlan = plan_destruction(
                    request=DestructionRequest(
                        operation=request.operation,
                        target=target,
                        database=database or "",
                        metadata_database=database or "",
                        pipeline_names=requested_names,
                        included_dependent_pipeline_names=included_names,
                    ),
                    analysis=analysis,
                    connection=connection,
                )
            require_destruction_authorization(
                analysis=analysis,
                request=http_request,
                context=authorization,
                operation=request.operation,
                affected_pipelines=plan.affected_pipeline_names,
            )
            store.save(plan=plan, actor=str(actor.principal.user_id))
            return _plan_payload(plan)
        except DestructionDependencyError as error:
            with state.query_lock:
                blocked_plan: DestructionPlan = plan_destruction(
                    request=DestructionRequest(
                        operation=request.operation,
                        target=target,
                        database=database or "",
                        metadata_database=database or "",
                        pipeline_names=requested_names,
                        included_dependent_pipeline_names=tuple(
                            sorted({*included_names, *error.dependent_pipeline_names})
                        ),
                    ),
                    analysis=analysis,
                    connection=connection,
                )
            require_destruction_authorization(
                analysis=analysis,
                request=http_request,
                context=authorization,
                operation=request.operation,
                affected_pipelines=blocked_plan.affected_pipeline_names,
            )
            return {
                **_plan_payload(blocked_plan),
                "selectedPipelines": list(requested_names),
                "requiredDependentPipelines": list(error.dependent_pipeline_names),
                "blocked": True,
            }
        except DestructionExternalDependencyError as error:
            raise HTTPException(
                status_code=_HTTP_CONFLICT,
                detail={
                    "message": str(error),
                    "blockingRelations": list(error.relation_names),
                },
            ) from error
        except (DestructionSelectionError, ValueError) as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except AdapterError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    def read_plan(*, http_request: Request, plan_id: str) -> dict[str, object]:
        actor: AuthenticatedRequest = _actor(http_request)
        try:
            plan: DestructionPlan = store.get(plan_id=plan_id, actor=str(actor.principal.user_id))
        except DestructionPlanExpiredError as error:
            raise HTTPException(status_code=_HTTP_GONE, detail=str(error)) from error
        except DestructionPlanNotFoundError as error:
            raise HTTPException(status_code=_HTTP_NOT_FOUND, detail=str(error)) from error
        except DestructionPlanCorruptError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        require_destruction_authorization(
            analysis=servable_analysis(),
            request=http_request,
            context=authorization,
            operation=plan.operation.value,
            affected_pipelines=plan.affected_pipeline_names,
        )
        return _plan_payload(plan)

    def review_plan(*, http_request: Request, plan_id: str) -> dict[str, object]:
        actor: AuthenticatedRequest = _actor(http_request)
        actor_id: str = str(actor.principal.user_id)
        try:
            plan: DestructionPlan = store.get(plan_id=plan_id, actor=actor_id)
            _authorize_plan(
                plan=plan,
                analysis=servable_analysis(),
                database=database,
                http_request=http_request,
                authorization=authorization,
            )
            reviewed_at: datetime = store.mark_reviewed(plan_id=plan_id, actor=actor_id)
        except DestructionPlanExpiredError as error:
            raise HTTPException(status_code=_HTTP_GONE, detail=str(error)) from error
        except DestructionPlanNotFoundError as error:
            raise HTTPException(status_code=_HTTP_NOT_FOUND, detail=str(error)) from error
        except DestructionPlanCorruptError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        except DestructionDriftError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        return {**_plan_payload(plan), "reviewedAt": reviewed_at.isoformat()}

    app.post("/api/destruction/plans")(create_plan)
    app.get("/api/destruction/plans/{plan_id}")(read_plan)
    app.post("/api/destruction/plans/{plan_id}/review")(review_plan)
    return app


def _register_destruction_execution_route(
    *,
    app: FastAPI,
    state: DevServerState,
    warehouse: WarehouseRuntime,
    database: str | None,
    project_dir: Path,
    authorization: OperationAuthorizationContext,
    servable_analysis: Callable[[], CompileAnalysis],
    store: DestructionPlanStore,
) -> FastAPI:
    """Attach the reviewed frozen-plan execution route."""

    def execute_plan(
        *,
        http_request: Request,
        plan_id: str,
        request: DestructionExecutionRequest,
    ) -> dict[str, object]:
        actor: AuthenticatedRequest = _actor(http_request)
        actor_id: str = str(actor.principal.user_id)
        connection: AdapterConnection = _required_connection(warehouse=warehouse, database=database)
        try:
            plan: DestructionPlan = store.get(plan_id=plan_id, actor=actor_id)
            _authorize_plan(
                plan=plan,
                analysis=servable_analysis(),
                database=database,
                http_request=http_request,
                authorization=authorization,
            )
            reviewed_at: datetime = store.reviewed_at(plan_id=plan_id, actor=actor_id)
            observation_connection: AdapterConnection | None = warehouse.observation_connection
            if observation_connection is None:
                raise HTTPException(
                    status_code=_HTTP_SERVICE_UNAVAILABLE,
                    detail="no warehouse observation connection",
                )
            with state.query_lock:
                result: DestructionExecutionResult = execute_destruction(
                    frozen_plan=plan,
                    actor_id=actor_id,
                    actor_name=actor.principal.username,
                    challenge_responses=tuple(request.responses),
                    reviewed_at=reviewed_at,
                    store=store,
                    connection=connection,
                    observation_connection=observation_connection,
                    project_dir=project_dir,
                    replan=lambda: _fresh_plan(
                        state=state,
                        plan=plan,
                        connection=connection,
                        database=database,
                        http_request=http_request,
                        authorization=authorization,
                    ),
                )
            state.snapshot.invalidate()
            return _result_payload(result)
        except DestructionPlanExpiredError as error:
            raise HTTPException(status_code=_HTTP_GONE, detail=str(error)) from error
        except DestructionPlanNotFoundError as error:
            raise HTTPException(status_code=_HTTP_NOT_FOUND, detail=str(error)) from error
        except DestructionPlanCorruptError as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error
        except DestructionChallengeError as error:
            raise HTTPException(status_code=_HTTP_BAD_REQUEST, detail=str(error)) from error
        except (DestructionPlanNotReviewedError, DestructionDriftError) as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        except AdapterTargetMutationLockError as error:
            raise HTTPException(status_code=_HTTP_CONFLICT, detail=str(error)) from error
        except (AdapterError, DestructionRecordingError) as error:
            raise HTTPException(status_code=_HTTP_BAD_GATEWAY, detail=str(error)) from error

    app.post("/api/destruction/plans/{plan_id}/execute")(execute_plan)
    return app


def _fresh_plan(
    *,
    state: DevServerState,
    plan: DestructionPlan,
    connection: AdapterConnection,
    database: str | None,
    http_request: Request,
    authorization: OperationAuthorizationContext,
) -> DestructionPlan:
    outcome: CompileOutcome = state.reload()
    if outcome.analysis is None:
        raise DestructionDriftError("Project compilation changed or failed after plan review")
    _authorize_plan(
        plan=plan,
        analysis=outcome.analysis,
        database=database,
        http_request=http_request,
        authorization=authorization,
    )
    return plan_destruction(
        request=DestructionRequest(
            operation=plan.operation,
            target=plan.target,
            database=plan.database,
            metadata_database=plan.metadata_database,
            pipeline_names=plan.requested_pipeline_names,
            included_dependent_pipeline_names=plan.included_dependent_pipeline_names,
        ),
        analysis=outcome.analysis,
        connection=connection,
    )


def _authorize_plan(
    *,
    plan: DestructionPlan,
    analysis: CompileAnalysis,
    database: str | None,
    http_request: Request,
    authorization: OperationAuthorizationContext,
) -> None:
    current_target: str = (
        analysis.compiled_project.target_name or authorization.selected_target or ""
    )
    if plan.target != current_target or plan.database != (database or ""):
        raise DestructionDriftError(
            "Destruction plan target or physical database differs from the active server target"
        )
    require_destruction_authorization(
        analysis=analysis,
        request=http_request,
        context=authorization,
        operation=plan.operation.value,
        affected_pipelines=plan.affected_pipeline_names,
    )


def _required_connection(*, warehouse: WarehouseRuntime, database: str | None) -> AdapterConnection:
    connection: AdapterConnection | None = warehouse.connection
    if connection is None or database is None:
        raise HTTPException(
            status_code=_HTTP_SERVICE_UNAVAILABLE,
            detail="no warehouse connection",
        )
    return connection


def _actor(request: Request) -> AuthenticatedRequest:
    return read_authenticated_request(request=request)


def _plan_payload(plan: DestructionPlan) -> dict[str, object]:
    return {
        "planId": plan.plan_id,
        "planFingerprint": plan.plan_fingerprint,
        "operation": plan.operation.value,
        "target": plan.target,
        "database": plan.database,
        "selectedPipelines": list(plan.requested_pipeline_names),
        "includedDependentPipelines": list(plan.included_dependent_pipeline_names),
        "affectedPipelines": list(plan.affected_pipeline_names),
        "requiredDependentPipelines": [],
        "blocked": False,
        "models": list(plan.affected_model_names),
        "resources": [
            {
                "name": relation.name,
                "kind": str(relation.kind),
                "logicalName": relation.logical_names[0],
                "logicalNames": list(relation.logical_names),
                "pipelineName": relation.pipeline_names[0] if relation.pipeline_names else None,
                "exists": relation.exists,
                "bytes": relation.total_bytes,
                "activeParts": relation.active_parts,
            }
            for relation in plan.relations
        ],
        "managedSourcesIncluded": not plan.preserves_sources,
        "retainedReplayDataIncluded": not plan.preserves_replay_data,
        "estimatedBytes": plan.estimated_bytes,
        "challengeValues": list(plan.challenges),
        "expiresAt": plan.expires_at.isoformat(),
    }


def _result_payload(result: DestructionExecutionResult) -> dict[str, object]:
    return {
        "invocationId": result.invocation_id,
        "status": result.outcome,
        "completedStatementSequences": list(result.completed_statement_sequences),
        "pendingStatementSequences": list(result.pending_statement_sequences),
        "remainingObjects": (
            None
            if result.remaining_relation_names is None
            else list(result.remaining_relation_names)
        ),
        "residualCatalogStatus": result.residual_catalog_status,
        "residualCatalogError": result.residual_catalog_error,
        "error": result.error_message,
    }
