"""Resolve audit warmup against existing warehouse-native model history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterDirectFingerprintSnapshot,
)
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.executor.auditing.models import AuditWarmupState, SqlAuditResult


def load_model_anchors_impl(
    *,
    client: AdapterConnection,
    metadata_database: str,
    target_database: str,
    model_names: tuple[str, ...],
    virtual_environments: bool,
) -> dict[str, str]:
    """Load latest successful apply or publication timestamps by logical model."""

    if virtual_environments:
        inventory: AdapterDeploymentInventory = client.load_deployment_inventory(metadata_database)
        anchors: dict[str, str] = {}
        for event in inventory.publish_events:
            for model_name in event.logical_view_names:
                if model_name in model_names and event.published_at > anchors.get(model_name, ""):
                    anchors[model_name] = event.published_at
        return anchors
    snapshot: AdapterDirectFingerprintSnapshot = client.load_direct_fingerprints(
        database=metadata_database,
        logical_model_identities=tuple(
            f"{target_database}.{model_name}" for model_name in model_names
        ),
    )
    return {
        record.logical_model_identity.removeprefix(f"{target_database}."): record.applied_at
        for record in snapshot.baselines
        if record.applied_at is not None
    }


def resolve_audit_warmup_states_impl(
    *,
    audits: tuple[LoadedSqlAudit, ...],
    anchors_by_model: dict[str, str],
    materialized_model_names: frozenset[str],
    warehouse_now: str,
) -> dict[str, AuditWarmupState]:
    """Calculate warmup eligibility from the newest anchor across each audit's refs."""

    now: datetime = _timestamp(warehouse_now)
    states: dict[str, AuditWarmupState] = {}
    for audit in audits:
        node_name: str = audit.name or audit.file_path.stem
        missing_model_names: tuple[str, ...] = tuple(
            model_name
            for model_name in audit.referenced_model_names
            if model_name not in anchors_by_model and model_name not in materialized_model_names
        )
        anchors: tuple[str, ...] = tuple(
            anchors_by_model[model_name]
            for model_name in audit.referenced_model_names
            if model_name in anchors_by_model
        )
        anchor: str | None = max(anchors, default=None)
        if missing_model_names:
            states[node_name] = AuditWarmupState(
                eligible=False,
                anchor=anchor,
                eligible_at=None,
                missing_model_names=missing_model_names,
            )
            continue
        if anchor is None or audit.warmup_seconds == 0:
            states[node_name] = AuditWarmupState(
                eligible=True,
                anchor=anchor,
                eligible_at=anchor,
            )
            continue
        eligible_at_value: datetime = _timestamp(anchor) + timedelta(seconds=audit.warmup_seconds)
        states[node_name] = AuditWarmupState(
            eligible=now >= eligible_at_value,
            anchor=anchor,
            eligible_at=_render_timestamp(eligible_at_value),
        )
    return states


def deferred_audit_result_impl(*, audit: LoadedSqlAudit, state: AuditWarmupState) -> SqlAuditResult:
    """Represent a warming audit without fabricating a pass or failure."""

    return SqlAuditResult(
        file_path=audit.file_path,
        referenced_model_names=audit.referenced_model_names,
        severity=audit.severity,
        passed=False,
        failing_row_count=0,
        sample_column_names=(),
        sample_rows=(),
        description=audit.description,
        name=audit.name,
        deferred_until=state.eligible_at,
        missing_relation_names=state.missing_model_names,
    )


def _timestamp(value: str) -> datetime:
    parsed: datetime = datetime.fromisoformat(value.replace(" ", "T").replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _render_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
