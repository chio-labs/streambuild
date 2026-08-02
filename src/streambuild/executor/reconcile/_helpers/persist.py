"""Persistence helpers for reconcile execution."""

from __future__ import annotations

from dataclasses import asdict

from streambuild.adapter.models import AdapterMetadataState
from streambuild.compiler.compile.models import DesiredMaterializedView, DesiredTable, DesiredView
from streambuild.compiler.planner.main.build_adapter_metadata_state import (
    build_adapter_metadata_state,
)
from streambuild.compiler.planner.main.build_normalized_fingerprint import (
    build_normalized_fingerprint,
)
from streambuild.compiler.planner.models import MetadataState, ObjectStateRecord
from streambuild.executor.reconcile.models import ReconcilePreview


def build_reconcile_metadata_state(preview: ReconcilePreview) -> AdapterMetadataState:
    """Build reconciled object-state metadata for persistence."""

    state: MetadataState = MetadataState(
        object_states=preview.eligible_records,
        deployments=(),
        deployment_watermarks=(),
        deployment_runtime_details=(),
        publish_events=(),
    )
    return build_adapter_metadata_state(state)


def build_object_state_record(
    *,
    desired_object: DesiredTable | DesiredMaterializedView | DesiredView,
    reconcile_id: str,
    recorded_at: str,
) -> ObjectStateRecord:
    normalized_query: str | None = (
        desired_object.query
        if isinstance(desired_object, (DesiredMaterializedView, DesiredView))
        else None
    )
    return ObjectStateRecord(
        deployment_id=reconcile_id,
        key=desired_object.key,
        normalized_fingerprint=build_normalized_fingerprint(asdict(desired_object.spec)),
        normalized_query=normalized_query,
        recorded_at=recorded_at,
    )
