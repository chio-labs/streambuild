"""Confirmation gate and execution of one previewed direct build."""

from __future__ import annotations

import sys
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.confirmation import confirm_build
from streambuild.cli.build._helpers.execution_artifacts import render_direct_execution_json
from streambuild.cli.build.models import BuildCommandOptions, DirectWorkflowPreparation
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.executor.direct.exceptions import DirectWorkflowExecutionError
from streambuild.executor.direct.main.build_direct_execution_result import (
    build_direct_execution_result,
)
from streambuild.executor.direct.main.execute_direct_build_workflow import (
    execute_direct_build_workflow,
)
from streambuild.executor.direct.main.persist_direct_fingerprints import (
    persist_direct_fingerprints,
)
from streambuild.executor.direct.models import (
    DirectBuildExecutionResult,
    DirectBuildRequest,
    DirectBuildWorkflow,
    DirectRuntimeExecution,
)
from streambuild.executor.workflow.models import BuildWorkflow, WorkflowExecutionResult
from streambuild.executor.workflow.types import WorkflowEventEmitter


def execute_confirmed_direct_build(
    *,
    preparation: DirectWorkflowPreparation,
    options: BuildCommandOptions,
    client: AdapterConnection,
    emitter: WorkflowEventEmitter | None = None,
) -> DirectBuildExecutionResult | None:
    """Show the destructive plan, require confirmation, then build."""

    if not confirm_build(options=options, plan_text=preparation.plan_text):
        print("Build cancelled.")
        return None
    try:
        runtime_execution: DirectRuntimeExecution = execute_direct_build_workflow(
            workflow=preparation.workflow,
            connection=client,
            emitter=emitter,
        )
    except DirectWorkflowExecutionError as error:
        artifact_warning: str | None = _publish_direct_build_artifact(
            target_dir=options.pipelines_root.parent / "target",
            workflow=error.workflow,
            execution_json=render_direct_execution_json(
                request=preparation.request,
                status="cancelled" if isinstance(error.cause, KeyboardInterrupt) else "failed",
                captures=error.captures,
                execution=error.partial_result,
                failed_step_id=error.failed_step_id,
                error_message=str(error.cause),
                audit_result=None,
            ),
        )
        _print_optional_warning(artifact_warning)
        applied_model_names: frozenset[str] = _applied_model_names(
            request=preparation.request,
            workflow=preparation.workflow,
            execution=error.partial_result,
        )
        fingerprint_warning: str | None = persist_direct_fingerprints(
            request=preparation.request,
            connection=client,
            applied_model_names=applied_model_names,
        )
        _print_optional_warning(fingerprint_warning)
        raise error.cause from error
    result: DirectBuildExecutionResult = build_direct_execution_result(
        request=preparation.request,
        execution=runtime_execution.execution,
        captures=runtime_execution.captures,
    )
    artifact_warning = _publish_direct_build_artifact(
        target_dir=options.pipelines_root.parent / "target",
        workflow=runtime_execution.workflow,
        execution_json=render_direct_execution_json(
            request=preparation.request,
            status="failed" if result.audit_result.error_failure_count else "succeeded",
            captures=runtime_execution.captures,
            execution=runtime_execution.execution,
            failed_step_id=None,
            error_message=None,
            audit_result=result.audit_result,
        ),
    )
    _print_optional_warning(artifact_warning)
    fingerprint_warning = persist_direct_fingerprints(
        request=preparation.request,
        connection=client,
    )
    _print_optional_warning(fingerprint_warning)
    return result


def _publish_direct_build_artifact(
    *, target_dir: Path, workflow: BuildWorkflow, execution_json: str
) -> str | None:
    try:
        _ = publish_build_workflow(
            target_dir=target_dir,
            workflow=workflow,
            execution_json=execution_json,
        )
    except OSError as error:
        return f"Direct build artifact was not recorded: {error}"
    return None


def _applied_model_names(
    *,
    request: DirectBuildRequest,
    workflow: DirectBuildWorkflow,
    execution: WorkflowExecutionResult,
) -> frozenset[str]:
    completed_step_ids: frozenset[str] = frozenset(
        result.step_id for result in execution.statement_results
    )
    replayed_root_names: frozenset[str] = frozenset(
        runtime.model_name
        for runtime in workflow.runtime_replays
        if runtime.replay_step_id in completed_step_ids
    )
    applied_model_names: set[str] = set()
    for replay_root in request.plan.replay_roots:
        if replay_root.model_key.name in replayed_root_names:
            applied_model_names.update(
                propagated_key.name for propagated_key in replay_root.propagated_model_keys
            )
    incomplete_runtime_models: set[str] = {
        runtime.model_name
        for runtime in workflow.runtime_replays
        if runtime.replay_step_id not in completed_step_ids
    }
    applied_model_names.difference_update(incomplete_runtime_models)
    return frozenset(applied_model_names)


def _print_optional_warning(warning: str | None) -> None:
    if warning is not None:
        print(warning, file=sys.stderr)
