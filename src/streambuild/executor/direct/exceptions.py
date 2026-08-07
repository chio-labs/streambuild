"""Direct-build execution failures."""

from streambuild.executor.direct.models import DirectReplayCapture
from streambuild.executor.workflow.models import BuildWorkflow, WorkflowExecutionResult


class DirectBuildError(RuntimeError):
    """Raised when a direct build cannot proceed safely."""


class DirectWorkflowExecutionError(DirectBuildError):
    """Raised with exact attempted SQL when a direct runtime workflow fails."""

    def __init__(
        self,
        *,
        workflow: BuildWorkflow,
        partial_result: WorkflowExecutionResult,
        captures: tuple[DirectReplayCapture, ...],
        failed_step_id: str,
        cause: BaseException,
    ) -> None:
        super().__init__(str(cause))
        self.workflow: BuildWorkflow = workflow
        self.partial_result: WorkflowExecutionResult = partial_result
        self.captures: tuple[DirectReplayCapture, ...] = captures
        self.failed_step_id: str = failed_step_id
        self.cause: BaseException = cause
