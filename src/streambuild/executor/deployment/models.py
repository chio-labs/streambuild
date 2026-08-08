"""Deployment inventory models."""

from dataclasses import dataclass

from streambuild.executor.deployment.types import DeploymentLifecycleState


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
class RelationStorage:
    """Row and byte totals for one warehouse relation."""

    rows: int = 0
    bytes: int = 0
