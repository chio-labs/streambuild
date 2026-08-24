"""Reconcile execution entrypoint."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterMetadataState
from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.planner.models import ActualState
from streambuild.executor.reconcile._helpers.persist import build_reconcile_metadata_state
from streambuild.executor.reconcile._helpers.preview import build_reconcile_preview
from streambuild.executor.reconcile._helpers.workflow import assemble_reconcile_workflow
from streambuild.executor.reconcile.models import ReconcilePreview, ReconcileResult
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.main.target_mutation_lock import target_mutation_lock
from streambuild.executor.workflow.models import WarehouseStatement


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
