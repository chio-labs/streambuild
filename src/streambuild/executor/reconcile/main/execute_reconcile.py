"""Reconcile execution entrypoint."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.executor.reconcile._helpers.persist import apply_reconcile
from streambuild.executor.reconcile._helpers.preview import build_reconcile_preview
from streambuild.executor.reconcile.models import ReconcilePreview, ReconcileResult


def execute_reconcile(
    *,
    client: AdapterConnection,
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
        return apply_reconcile(client=client, preview=preview)
    return preview
