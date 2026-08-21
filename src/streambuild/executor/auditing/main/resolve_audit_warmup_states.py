"""Calculate audit warmup eligibility."""

from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.executor.auditing._helpers.warmup import resolve_audit_warmup_states_impl
from streambuild.executor.auditing.models import AuditWarmupState


def resolve_audit_warmup_states(
    *,
    audits: tuple[LoadedSqlAudit, ...],
    anchors_by_model: dict[str, str],
    materialized_model_names: frozenset[str],
    warehouse_now: str,
) -> dict[str, AuditWarmupState]:
    """Calculate warmup eligibility from the newest anchor across each audit's refs."""

    return resolve_audit_warmup_states_impl(
        audits=audits,
        anchors_by_model=anchors_by_model,
        materialized_model_names=materialized_model_names,
        warehouse_now=warehouse_now,
    )
