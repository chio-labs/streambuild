"""Runtime models for janitor preview."""

from dataclasses import dataclass

from streambuild.executor.janitor.exceptions import JanitorInputError


@dataclass(frozen=True)
class JanitorPreviewCandidate:
    deployment_id: str
    created_at: str
    status: str
    logical_view_names: tuple[str, ...]
    physical_object_names: tuple[str, ...]
    deletable: bool
    reason: str


@dataclass(frozen=True)
class JanitorPreviewResult:
    database: str
    retention_days: int
    minimum_rollback_deployments: int
    candidates: tuple[JanitorPreviewCandidate, ...]


@dataclass(frozen=True)
class JanitorApplyResult:
    database: str
    retention_days: int
    minimum_rollback_deployments: int
    deleted_deployment_ids: tuple[str, ...]
    deleted_object_names: tuple[str, ...]


@dataclass(frozen=True)
class JanitorRequest:
    database: str
    metadata_database: str
    retention_days: int
    apply: bool
    minimum_rollback_deployments: int = 2

    def __post_init__(self) -> None:
        if self.retention_days < 0:
            raise JanitorInputError("retention_days must be non-negative")
        if self.minimum_rollback_deployments < 0:
            raise JanitorInputError("minimum_rollback_deployments must be non-negative")
