from streambuild.compiler.quality.types import QualityNodeKind
from streambuild.events.models import InvocationObservation, NodeResultObservation
from streambuild.executor.auditing.types import QualityResultStatus


def build_node_result_observation(
    *,
    node_kind: str = "audit",
    status: QualityResultStatus = QualityResultStatus.FAILED,
    result_id: str = "result-1",
    binding_key: str = "binding-1",
    target_identity: str = "prod",
    trigger: str = "scheduled",
    completed_at: str = "2024-01-01 00:00:01.000",
    payload_json: str = "{}",
) -> NodeResultObservation:
    return NodeResultObservation(
        result_id=result_id,
        invocation_id="invocation-1",
        node_kind=QualityNodeKind(node_kind),
        node_name="orders_fresh",
        binding_key=binding_key,
        target_identity=target_identity,
        trigger=trigger,
        status=status,
        severity="error",
        failure_count=2,
        completed_at=completed_at,
        scheduled_for=None,
        payload_json=payload_json,
        error_message=None,
    )


def build_invocation_observation(
    *,
    command: str = "build",
    invocation_id: str = "invocation-1",
    target_identity: str = "prod",
) -> InvocationObservation:
    return InvocationObservation(
        invocation_id=invocation_id,
        command=command,
        mode="virtual_environment",
        outcome="succeeded",
        exit_code=0,
        target_identity=target_identity,
        deployment_id=None,
        selected_node_count=3,
        error_message=None,
        completed_at="2024-01-01 00:00:02.000",
    )
