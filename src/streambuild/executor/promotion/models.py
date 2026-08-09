"""Publish runtime models."""

from dataclasses import dataclass

from streambuild.executor.promotion.exceptions import PublishExecutionError
from streambuild.executor.promotion.types import PromotionPreviewClassification, PublishOperation


@dataclass(frozen=True)
class PublishRequest:
    """Input required to publish a staged deployment."""

    deployment_id: str | None
    metadata_database: str
    default_database: str
    operation: PublishOperation | str = PublishOperation.PROMOTE
    previous_deployment_id: str | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "operation", PublishOperation(self.operation))
        except ValueError as error:
            raise PublishExecutionError(
                "publish operation must be 'promote' or 'rollback'"
            ) from error


@dataclass(frozen=True)
class PublishedView:
    """A stable logical view created or replaced during publish."""

    view_name: str
    target_table_name: str


@dataclass(frozen=True)
class PublishResult:
    """Result of publishing a staged deployment."""

    deployment_id: str
    published_views: tuple[PublishedView, ...]
    per_relation_atomic_replace: bool
    graph_atomic_publish: bool
    operation: PublishOperation | str = PublishOperation.PROMOTE
    previous_deployment_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", PublishOperation(self.operation))


@dataclass(frozen=True)
class PromotionBindingAddition:
    """One new stable logical binding created by promotion."""

    database: str
    logical_name: str
    physical_name: str


@dataclass(frozen=True)
class PromotionBindingReplacement:
    """One stable logical binding switched to a different physical relation."""

    database: str
    logical_name: str
    from_physical_name: str
    to_physical_name: str


@dataclass(frozen=True)
class PromotionBindingRemoval:
    """One obsolete live binding removed by promotion."""

    database: str
    logical_name: str
    physical_name: str


@dataclass(frozen=True)
class PromotionOrphanedRelation:
    """One formerly live physical relation left unbound after promotion."""

    database: str
    physical_name: str


@dataclass(frozen=True)
class DeploymentPromotionPreview:
    """Exact live-binding effects of one deployment promotion."""

    classification: PromotionPreviewClassification
    additions: tuple[PromotionBindingAddition, ...]
    replacements: tuple[PromotionBindingReplacement, ...]
    removals: tuple[PromotionBindingRemoval, ...]
    orphaned_relations: tuple[PromotionOrphanedRelation, ...]


@dataclass(frozen=True)
class RollbackRequest:
    """Input used to resolve one whole-deployment rollback."""

    deployment_id: str | None
    previous: bool
    metadata_database: str
    default_database: str

    def __post_init__(self) -> None:
        if (self.deployment_id is None) == (not self.previous):
            raise PublishExecutionError("rollback requires either a deployment ID or --previous")


@dataclass(frozen=True)
class RollbackPlan:
    """Resolved current and target publication identities for rollback."""

    current_deployment_id: str
    target_deployment_id: str
    logical_view_names: tuple[str, ...]
