"""Failures raised by destruction planning and confirmation."""


class DestructionError(RuntimeError):
    """Base error for the destruction domain."""


class DestructionSelectionError(DestructionError):
    """The requested pipeline selection is invalid."""


class DestructionValidationError(DestructionError, ValueError):
    """A destruction value violates a domain invariant."""


class DestructionResourceError(DestructionError, TypeError):
    """A manifest resource cannot participate in destruction."""


class DestructionConsistencyError(DestructionError):
    """Internal destruction evidence became inconsistent."""


class DestructionDependencyError(DestructionSelectionError):
    """Unselected downstream pipelines make destruction unsafe."""

    def __init__(self, dependent_pipeline_names: tuple[str, ...]) -> None:
        self.dependent_pipeline_names = dependent_pipeline_names
        super().__init__(
            "Unselected dependent or shared-source pipelines must be explicitly included: "
            f"{dependent_pipeline_names!r}"
        )


class DestructionExternalDependencyError(DestructionSelectionError):
    """Warehouse relations outside the owned scope depend on planned relations."""

    def __init__(self, relation_names: tuple[str, ...]) -> None:
        self.relation_names: tuple[str, ...] = relation_names
        super().__init__(f"Unmanaged warehouse dependants block destruction: {relation_names!r}")


class DestructionPlanNotFoundError(DestructionError):
    """The requested frozen plan does not exist or was already consumed."""


class DestructionPlanExpiredError(DestructionError):
    """The requested frozen plan has expired."""


class DestructionPlanNotReviewedError(DestructionError):
    """The frozen plan has not passed the explicit review gate."""


class DestructionPlanCorruptError(DestructionError):
    """A durable frozen-plan record is incompatible or corrupt."""


class DestructionChallengeError(DestructionError):
    """Typed challenge responses do not exactly match the frozen plan."""


class DestructionDriftError(DestructionError):
    """A freshly planned operation differs from its frozen plan."""


class DestructionRecordingError(DestructionError):
    """Required destructive-operation evidence could not be persisted."""


class DestructionRecoveryError(DestructionError):
    """A failed run does not contain valid recoverable destruction intent."""


class DestructionRecoveryNotFoundError(DestructionRecoveryError):
    """A run is not a recoverable operation in the active project."""
