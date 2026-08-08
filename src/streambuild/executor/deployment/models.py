"""Deployment inventory models."""

from dataclasses import dataclass

from streambuild.executor.deployment.types import DeploymentDiffStatus, DeploymentLifecycleState


@dataclass(frozen=True)
class DeploymentSummary:
    """One deployment reconstructed from authoritative warehouse evidence."""

    deployment_id: str
    state: DeploymentLifecycleState
    created_at: str | None
    persisted_status: str | None
    root_names: tuple[str, ...]
    physical_relation_names: tuple[str, ...]
    missing_physical_relation_names: tuple[str, ...]
    active_binding_names: tuple[str, ...]
    latest_published_at: str | None


@dataclass(frozen=True)
class DeploymentInventory:
    """Deterministically ordered deployment summaries for one target database."""

    database: str
    deployments: tuple[DeploymentSummary, ...]


@dataclass(frozen=True)
class DeploymentDiffRequest:
    """One active/deployment comparison expression."""

    database: str
    metadata_database: str
    comparison: str


@dataclass(frozen=True)
class DeploymentDiffColumn:
    """One catalog column included in a deployment comparison."""

    name: str
    type: str
    default_expression: str | None


@dataclass(frozen=True)
class DeploymentDiffRelation:
    """Schema and count comparison for one logical relation."""

    database: str
    logical_name: str
    status: DeploymentDiffStatus | str
    from_physical_name: str | None
    to_physical_name: str | None
    from_columns: tuple[DeploymentDiffColumn, ...]
    to_columns: tuple[DeploymentDiffColumn, ...]
    from_row_count: int | None
    to_row_count: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", DeploymentDiffStatus(self.status))


@dataclass(frozen=True)
class DeploymentDiffResult:
    """Resolved endpoints and per-relation deployment differences."""

    database: str
    from_endpoint: str
    to_endpoint: str
    relations: tuple[DeploymentDiffRelation, ...]
