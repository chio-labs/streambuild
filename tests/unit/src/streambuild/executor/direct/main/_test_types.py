from dataclasses import dataclass

from streambuild.executor.workflow.types import WorkflowPhase


@dataclass(frozen=True)
class DirectWorkflowTestCase:
    description: str
    expected_first_phase: WorkflowPhase
    expected_last_phase: WorkflowPhase
    expected_replay_count: int
    expected_boundary_model_segments: tuple[str, ...]
