"""Construct one bounded audit or test result observation."""

from hashlib import sha256

from streambuild.adapter.models import AdapterInvocationRecord, AdapterNodeResultRecord
from streambuild.executor.observability._helpers.payload import bounded_json, concise_error
from streambuild.executor.observability.main.build_definition_fingerprint import (
    build_definition_fingerprint,
)


def build_node_result_record(
    *,
    invocation: AdapterInvocationRecord,
    node_kind: str,
    node_identity: str,
    definition: str,
    status: str,
    severity: str | None,
    failure_count: int,
    payload: dict[str, object],
    error_message: str | None,
) -> AdapterNodeResultRecord:
    """Build one immutable bounded audit or test result row."""

    definition_fingerprint: str = build_definition_fingerprint(
        definition=definition, severity=severity
    )
    result_id: str = sha256(
        f"{invocation.invocation_id}:{node_kind}:{node_identity}:{definition_fingerprint}".encode()
    ).hexdigest()
    return AdapterNodeResultRecord(
        result_id=result_id,
        invocation_id=invocation.invocation_id,
        node_kind=node_kind,
        node_identity=node_identity,
        definition_fingerprint=definition_fingerprint,
        target_identity=invocation.target_identity,
        status=status,
        severity=severity,
        failure_count=failure_count,
        completed_at=invocation.completed_at,
        payload_json=bounded_json(payload),
        error_message=concise_error(error_message),
    )
