"""Errors raised by workflow construction and execution."""


class WorkflowValidationError(ValueError):
    """Raised when workflow statements violate ordering or byte contracts."""


class WorkflowExecutionError(RuntimeError):
    """Raised with completed statement evidence when one workflow statement fails."""

    def __init__(self, *, failed_step_id: str, partial_result: object, cause: Exception) -> None:
        super().__init__(str(cause))
        self.failed_step_id: str = failed_step_id
        self.partial_result: object = partial_result
        self.cause: Exception = cause
