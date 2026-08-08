"""Construct one bounded audit or test result observation."""

from hashlib import sha256

from streambuild.adapter.models import AdapterInvocationRecord, AdapterNodeResultRecord
from streambuild.compiler.quality.models import QualityNodeIdentity
from streambuild.executor.observability._helpers.payload import bounded_json, concise_error
from streambuild.executor.observability.models import QualityResultContext


def build_node_result_record(
    *,
    invocation: AdapterInvocationRecord,
    identity: QualityNodeIdentity,
    context: QualityResultContext,
    status: str,
    severity: str | None,
    failure_count: int,
    payload: dict[str, object],
    error_message: str | None,
) -> AdapterNodeResultRecord:
    """Build one immutable bounded audit or test result row."""

    result_id: str = sha256(
        (
            f"{invocation.invocation_id}:{identity.node_kind}:{identity.node_name}:"
            f"{identity.binding_key}:{identity.definition_fingerprint}:"
            f"{identity.execution_fingerprint}"
        ).encode()
    ).hexdigest()
    return AdapterNodeResultRecord(
        result_id=result_id,
        invocation_id=invocation.invocation_id,
        node_kind=identity.node_kind,
        node_name=identity.node_name,
        binding_key=identity.binding_key,
        definition_fingerprint=identity.definition_fingerprint,
        execution_fingerprint=identity.execution_fingerprint,
        target_identity=invocation.target_identity,
        trigger=str(context.trigger),
        scheduled_for=context.scheduled_for,
        cadence_seconds=context.cadence_seconds,
        warmup_seconds=context.warmup_seconds,
        status=status,
        severity=severity,
        failure_count=failure_count,
        completed_at=invocation.completed_at,
        payload_json=bounded_json(payload),
        error_message=concise_error(error_message),
    )
