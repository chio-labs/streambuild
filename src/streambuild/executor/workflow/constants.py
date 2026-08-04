"""Stable workflow validation constants."""

from streambuild.executor.workflow.types import WorkflowPhase

WORKFLOW_PHASE_ORDER: tuple[WorkflowPhase, ...] = (
    WorkflowPhase.PREFLIGHT,
    WorkflowPhase.PREPARATION,
    WorkflowPhase.TEARDOWN,
    WorkflowPhase.REALIZATION,
    WorkflowPhase.STABILIZATION,
    WorkflowPhase.BOUNDARY,
    WorkflowPhase.REPLAY,
    WorkflowPhase.AUDIT,
    WorkflowPhase.FINALIZATION,
)
