"""Execute a reviewed, actor-bound destruction plan with durable evidence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterInvocationRecord,
    AdapterMutationResult,
    AdapterTargetMutationLock,
)
from streambuild.executor.destruction._helpers.drift import verify_destruction_drift
from streambuild.executor.destruction._helpers.ordering import (
    reverse_topologically_order_relations,
)
from streambuild.executor.destruction._helpers.workflow import assemble_destruction_workflow
from streambuild.executor.destruction.constants import RESIDUAL_CATALOG_STATUS_OBSERVED
from streambuild.executor.destruction.exceptions import (
    DestructionConsistencyError,
    DestructionRecordingError,
)
from streambuild.executor.destruction.models import (
    DestructionExecutionResult,
    DestructionPlan,
    DestructionRecordingContext,
    DestructionRelationEvidence,
)
from streambuild.executor.destruction.types import DestructionOperation, DestructionPlanStore
from streambuild.executor.observability.classes.run_event_sink import RunEventSink
from streambuild.executor.observability.main.build_invocation_record import (
    build_invocation_record,
)
from streambuild.executor.observability.main.initialize_observability import (
    initialize_observability,
)
from streambuild.executor.observability.main.logical_project_identity import (
    logical_project_identity,
)
from streambuild.executor.observability.main.persist_terminal_observations import (
    persist_terminal_observations,
)
from streambuild.executor.observability.main.start_invocation import start_invocation
from streambuild.executor.observability.models import TerminalInvocation
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import (
    WarehouseStatement,
    WorkflowExecutionResult,
    WorkflowStatementResult,
)


def execute_destruction(
    *,
    frozen_plan: DestructionPlan,
    actor_id: str,
    actor_name: str,
    challenge_responses: tuple[str, ...],
    reviewed_at: datetime,
    store: DestructionPlanStore,
    connection: AdapterConnection,
    observation_connection: AdapterConnection,
    project_dir: Path,
    replan: Callable[[], DestructionPlan],
) -> DestructionExecutionResult:
    """Record exact intent, consume once under the target lock, and execute."""

    started: tuple[str, str, int] = start_invocation()
    invocation_id: str = started[0]
    lock: AdapterTargetMutationLock | None = None
    sink: RunEventSink | None = None
    statements: tuple[WarehouseStatement, ...] = ()
    current_plan: DestructionPlan = frozen_plan
    recording_context: DestructionRecordingContext | None = None
    confirmed_at: datetime = datetime.now(tz=UTC)
    execution_dispatched: bool = False
    failure_phase: str = "pre_execution"
    try:
        initialize_observability(
            connection=observation_connection,
            database=frozen_plan.metadata_database,
        )
        lock = connection.acquire_target_mutation_lock(
            database=frozen_plan.database,
            owner_id=invocation_id,
        )
        current_plan = frozen_plan
        statements = assemble_destruction_workflow(
            plan=current_plan,
            connection=connection,
        )
        sink = RunEventSink(
            connection=observation_connection,
            database=current_plan.metadata_database,
            invocation_id=invocation_id,
            project_identity=logical_project_identity(project_dir=project_dir),
            strict_persistence=True,
        )
        recording_context = DestructionRecordingContext(
            plan=current_plan,
            actor_id=actor_id,
            actor_name=actor_name,
            reviewed_at=reviewed_at,
            confirmed_at=confirmed_at,
            challenge_responses=challenge_responses,
            connection=connection,
            observation_connection=observation_connection,
            project_dir=project_dir,
            started=started,
            statements=statements,
            sink=sink,
        )
        initial_evidence: dict[str, object] = _operation_evidence(
            context=recording_context,
            completed_sequences=(),
            pending_sequences=tuple(statement.sequence for statement in statements),
            remaining=tuple(
                relation.name for relation in current_plan.relations if relation.exists
            ),
            residual_catalog_status="not_mutated",
            residual_catalog_error=None,
            failure_phase=None,
        )
        sink.set_operation_evidence(initial_evidence)
        sink.run_started(
            command=_command(current_plan.operation),
            mode="destructive",
            total_statements=len(statements),
            selected_node_count=len(current_plan.affected_model_names),
            selectors=tuple(f"pipeline:{name}" for name in current_plan.requested_pipeline_names),
            executed_logical_ids=tuple(
                f"model:{name}" for name in current_plan.affected_model_names
            ),
        )
        workflow_sha256: str = sha256(
            "\n".join(item.sql for item in statements).encode()
        ).hexdigest()
        failure_phase = "workflow_prepared"
        sink.workflow_prepared(statements=statements, workflow_sha256=workflow_sha256)

        failure_phase = "locked_replan"
        _ = verify_destruction_drift(
            frozen_plan=frozen_plan,
            replan=replan,
        )
        failure_phase = "plan_consumption"
        consumed_plan: DestructionPlan = store.consume(
            plan_id=frozen_plan.plan_id,
            challenge_responses=challenge_responses,
            actor=actor_id,
        )
        if consumed_plan.plan_fingerprint != current_plan.plan_fingerprint:
            raise DestructionConsistencyError(
                "Consumed destruction plan differs from the locked replan"
            )
        execution_dispatched = True
        return _execute_recorded_plan(context=recording_context)
    except (Exception, KeyboardInterrupt) as error:
        if recording_context is not None and statements and not execution_dispatched:
            try:
                _ = _record_terminal(
                    context=recording_context,
                    execution=WorkflowExecutionResult(statement_results=()),
                    remaining=tuple(
                        relation.name for relation in current_plan.relations if relation.exists
                    ),
                    residual_catalog_status="not_mutated",
                    residual_catalog_error=None,
                    error_message=str(error),
                    failure_phase=failure_phase,
                )
            except DestructionRecordingError:
                raise
        raise
    finally:
        if sink is not None:
            sink.stop()
        if lock is not None:
            connection.release_target_mutation_lock(lock)


def _execute_recorded_plan(*, context: DestructionRecordingContext) -> DestructionExecutionResult:
    execution: WorkflowExecutionResult
    error_message: str | None = None
    failure_phase: str | None = None
    interruption: KeyboardInterrupt | None = None
    try:
        execution = execute_warehouse_workflow(
            statements=context.statements,
            connection=context.connection,
            emitter=context.sink,
        )
    except WorkflowExecutionError as error:
        if not isinstance(error.partial_result, WorkflowExecutionResult):
            raise DestructionConsistencyError(
                "Destruction workflow did not provide an exact partial result"
            ) from error
        execution = error.partial_result
        _verify_completed_prefix(statements=context.statements, execution=execution)
        recovery_error: str | None = None
        if isinstance(error.cause, KeyboardInterrupt):
            try:
                execution = _recover_interrupted_drop(
                    context=context,
                    execution=execution,
                    failed_step_id=error.failed_step_id,
                )
            except Exception as interrupted_recovery_failure:
                recovery_error = str(interrupted_recovery_failure)
        error_message = str(error)
        failure_phase = "warehouse_execution"
        if isinstance(error.cause, KeyboardInterrupt):
            interruption = error.cause
        if recovery_error is not None:
            error_message = (
                f"{error_message}; interrupted DROP reconciliation failed: {recovery_error}"
            )
            failure_phase = "drop_reconciliation"
    except Exception as error:
        execution = WorkflowExecutionResult(statement_results=())
        error_message = str(error)
        failure_phase = "warehouse_execution"

    _verify_completed_prefix(statements=context.statements, execution=execution)
    remaining: tuple[str, ...] | None
    residual_catalog_status: str
    residual_catalog_error: str | None = None
    try:
        remaining = _remaining_relations(plan=context.plan, connection=context.connection)
        residual_catalog_status = RESIDUAL_CATALOG_STATUS_OBSERVED
    except Exception as error:
        remaining = None
        residual_catalog_status = "unavailable"
        residual_catalog_error = str(error)
        error_message = (
            f"Residual catalog inspection failed: {error}"
            if error_message is None
            else f"{error_message}; residual catalog inspection failed: {error}"
        )
        failure_phase = "residual_catalog"
    if error_message is None and remaining:
        error_message = "Planned relations remain after destructive workflow completion"
        failure_phase = "residual_catalog"

    result: DestructionExecutionResult = _record_terminal(
        context=context,
        execution=execution,
        remaining=remaining,
        residual_catalog_status=residual_catalog_status,
        residual_catalog_error=residual_catalog_error,
        error_message=error_message,
        failure_phase=failure_phase,
    )
    if interruption is not None:
        raise interruption
    return result


def _recover_interrupted_drop(
    *,
    context: DestructionRecordingContext,
    execution: WorkflowExecutionResult,
    failed_step_id: str,
) -> WorkflowExecutionResult:
    prefix: str = "destroy_relation_"
    if not failed_step_id.startswith(prefix):
        return execution
    relation_index: int = int(failed_step_id.removeprefix(prefix)) - 1
    ordered_relations: tuple[DestructionRelationEvidence, ...] = tuple(
        relation
        for relation in reverse_topologically_order_relations(context.plan.relations)
        if relation.exists
    )
    relation: DestructionRelationEvidence = ordered_relations[relation_index]
    remaining: tuple[str, ...] = _remaining_relations(
        plan=context.plan,
        connection=context.connection,
    )
    if relation.name in remaining:
        return execution
    failed_statement_index: int = next(
        index
        for index, statement in enumerate(context.statements)
        if statement.step_id == failed_step_id
    )
    if len(execution.statement_results) != failed_statement_index:
        raise DestructionConsistencyError(
            "Interrupted DROP did not align with the confirmed workflow prefix"
        )
    synthetic_drop: WorkflowStatementResult = WorkflowStatementResult(
        step_id=failed_step_id,
        query_result=None,
        mutation_result=AdapterMutationResult(),
        error_message=None,
    )
    return WorkflowExecutionResult(statement_results=(*execution.statement_results, synthetic_drop))


def _record_terminal(
    *,
    context: DestructionRecordingContext,
    execution: WorkflowExecutionResult,
    remaining: tuple[str, ...] | None,
    residual_catalog_status: str,
    residual_catalog_error: str | None,
    error_message: str | None,
    failure_phase: str | None,
) -> DestructionExecutionResult:
    _verify_completed_prefix(statements=context.statements, execution=execution)
    completed_count: int = len(execution.statement_results)
    completed_sequences: tuple[int, ...] = tuple(
        statement.sequence for statement in context.statements[:completed_count]
    )
    pending_sequences: tuple[int, ...] = tuple(
        statement.sequence for statement in context.statements[completed_count:]
    )
    succeeded: bool = (
        error_message is None
        and residual_catalog_status == RESIDUAL_CATALOG_STATUS_OBSERVED
        and remaining == ()
        and not pending_sequences
    )
    outcome: str = "succeeded" if succeeded else "failed"
    exit_code: int = 0 if succeeded else 1
    summary: dict[str, object] = _operation_evidence(
        context=context,
        completed_sequences=completed_sequences,
        pending_sequences=pending_sequences,
        remaining=remaining,
        residual_catalog_status=residual_catalog_status,
        residual_catalog_error=residual_catalog_error,
        failure_phase=failure_phase,
    )
    context.sink.set_operation_evidence(summary)
    run_completed_error: str | None = None
    try:
        context.sink.run_completed(
            outcome=outcome,
            exit_code=exit_code,
            error_message=error_message,
        )
    except Exception as error:
        run_completed_error = str(error)
        outcome = "failed"
        exit_code = 1
        error_message = (
            f"Run completion evidence failed: {error}"
            if error_message is None
            else f"{error_message}; run completion evidence failed: {error}"
        )
        if failure_phase is None:
            failure_phase = "run_completed"
    finally:
        context.sink.stop()

    summary = _operation_evidence(
        context=context,
        completed_sequences=completed_sequences,
        pending_sequences=pending_sequences,
        remaining=remaining,
        residual_catalog_status=residual_catalog_status,
        residual_catalog_error=residual_catalog_error,
        failure_phase=failure_phase,
    )
    summary["runCompletedError"] = run_completed_error
    invocation: AdapterInvocationRecord = build_invocation_record(
        started=context.started,
        terminal=TerminalInvocation(
            project_dir=context.project_dir,
            target_identity=context.plan.target,
            command=_command(context.plan.operation),
            mode="destructive",
            outcome=outcome,
            exit_code=exit_code,
            materialized_outcome=(
                "applied"
                if any(
                    result.step_id.startswith("destroy_relation_")
                    for result in execution.statement_results
                )
                else None
            ),
            deployment_id=None,
            workflow_id=context.plan.plan_fingerprint,
            selected_node_count=len(context.plan.affected_model_names),
            error_message=error_message,
            summary=summary,
        ),
    )
    primary_warning: str | None = _persist_terminal(
        connection=context.observation_connection,
        plan=context.plan,
        invocation=invocation,
    )
    fallback_warning: str | None = None
    if primary_warning is not None and context.connection is not context.observation_connection:
        fallback_warning = _persist_terminal(
            connection=context.connection,
            plan=context.plan,
            invocation=invocation,
        )
    if primary_warning is not None and (
        context.connection is context.observation_connection or fallback_warning is not None
    ):
        detail: str = primary_warning
        if fallback_warning is not None:
            detail = f"{primary_warning}; fallback failed: {fallback_warning}"
        raise DestructionRecordingError(detail)
    return DestructionExecutionResult(
        invocation_id=context.started[0],
        outcome=outcome,
        completed_statement_sequences=completed_sequences,
        pending_statement_sequences=pending_sequences,
        remaining_relation_names=remaining,
        error_message=error_message,
        residual_catalog_status=residual_catalog_status,
        residual_catalog_error=residual_catalog_error,
    )


def _persist_terminal(
    *,
    connection: AdapterConnection,
    plan: DestructionPlan,
    invocation: AdapterInvocationRecord,
) -> str | None:
    try:
        return persist_terminal_observations(
            client=connection,
            database=plan.metadata_database,
            invocation=invocation,
            node_results=(),
        )
    except Exception as error:
        return f"Terminal observations were not recorded: {error}"


def _verify_completed_prefix(
    *, statements: tuple[WarehouseStatement, ...], execution: WorkflowExecutionResult
) -> None:
    expected: tuple[str, ...] = tuple(
        statement.step_id for statement in statements[: len(execution.statement_results)]
    )
    actual: tuple[str, ...] = tuple(result.step_id for result in execution.statement_results)
    if actual != expected:
        raise DestructionConsistencyError(
            "Destruction execution results are not an exact workflow prefix"
        )


def _operation_evidence(
    *,
    context: DestructionRecordingContext,
    completed_sequences: tuple[int, ...],
    pending_sequences: tuple[int, ...],
    remaining: tuple[str, ...] | None,
    residual_catalog_status: str,
    residual_catalog_error: str | None,
    failure_phase: str | None,
) -> dict[str, object]:
    plan: DestructionPlan = context.plan
    return {
        "actor": {"id": context.actor_id, "username": context.actor_name},
        "target": plan.target,
        "database": plan.database,
        "operationKind": plan.operation.value,
        "planId": plan.plan_id,
        "planFingerprint": plan.plan_fingerprint,
        "manifestFingerprint": plan.manifest_fingerprint,
        "originalSelection": list(plan.requested_pipeline_names),
        "includedDependentPipelines": list(plan.included_dependent_pipeline_names),
        "affectedPipelines": list(plan.affected_pipeline_names),
        "affectedModels": list(plan.affected_model_names),
        "affectedSources": list(plan.affected_source_names),
        "expectedChallenges": list(plan.challenges),
        "submittedChallenges": list(context.challenge_responses),
        "reviewedAt": context.reviewed_at.isoformat(),
        "confirmedAt": context.confirmed_at.isoformat(),
        "estimatedActivePartBytes": plan.estimated_bytes,
        "managedSourcesIncluded": not plan.preserves_sources,
        "retainedReplayDataIncluded": not plan.preserves_replay_data,
        "kafkaOffsetsReset": False,
        "plannedRelations": [
            {
                "database": relation.database,
                "name": relation.name,
                "kind": str(relation.kind),
                "catalogFingerprint": relation.catalog_fingerprint,
                "dependencies": list(relation.dependency_relation_names),
            }
            for relation in plan.relations
        ],
        "completedStatementSequences": list(completed_sequences),
        "pendingStatementSequences": list(pending_sequences),
        "remainingObjects": None if remaining is None else list(remaining),
        "residualCatalogStatus": residual_catalog_status,
        "residualCatalogError": residual_catalog_error,
        "failurePhase": failure_phase,
    }


def _remaining_relations(
    *, plan: DestructionPlan, connection: AdapterConnection
) -> tuple[str, ...]:
    names: frozenset[str] = connection.load_catalog(plan.database).relation_names()
    return tuple(sorted(relation.name for relation in plan.relations if relation.name in names))


def _command(operation: DestructionOperation) -> str:
    if operation == DestructionOperation.DESTROY_PIPELINES:
        return "destroy pipelines"
    return "reset target"
