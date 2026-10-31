"""Reconcile execution entrypoint."""

from __future__ import annotations

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.adapter.models import AdapterMetadataState
from sqltide.compiler.compile.models import DesiredState, ObjectKey
from sqltide.compiler.planner.models import ActualState
from sqltide.executor.reconcile._helpers.persist import build_reconcile_metadata_state
from sqltide.executor.reconcile._helpers.preview import build_reconcile_preview
from sqltide.executor.reconcile._helpers.workflow import assemble_reconcile_workflow
from sqltide.executor.reconcile.models import ReconcilePreview, ReconcileResult
from sqltide.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from sqltide.executor.workflow.main.target_mutation_lock import target_mutation_lock
from sqltide.executor.workflow.models import WarehouseStatement


def execute_reconcile(
    *,
    client: AdapterConnection,
    target_database: str,
    metadata_database: str,
    desired_state: DesiredState,
    actual_state: ActualState,
    selected_model_keys: frozenset[ObjectKey],
    apply: bool = False,
) -> ReconcilePreview | ReconcileResult:
    """Preview or apply reconcile for structurally compatible live targets."""

    preview: ReconcilePreview = build_reconcile_preview(
        metadata_database=metadata_database,
        desired_state=desired_state,
        actual_state=actual_state,
        selected_model_keys=selected_model_keys,
    )
    if apply:
        with target_mutation_lock(connection=client, database=target_database):
            metadata_state: AdapterMetadataState = build_reconcile_metadata_state(preview)
            statements: tuple[WarehouseStatement, ...] = assemble_reconcile_workflow(
                client=client,
                database=preview.database,
                metadata_state=metadata_state,
            )
            _ = execute_warehouse_workflow(statements=statements, connection=client)
            return ReconcileResult(
                database=preview.database,
                reconcile_id=preview.reconcile_id,
                reconciled_records=preview.eligible_records,
                rejected_targets=preview.rejected_targets,
            )
    return preview
