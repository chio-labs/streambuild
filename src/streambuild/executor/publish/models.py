"""Publish runtime models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PublishRequest:
    """Input required to publish a staged deployment."""

    deployment_id: str | None
    metadata_database: str
    default_database: str


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
