"""Publish execution entrypoint."""

from streambuild.executor.publish.helpers.metadata import persist_publish_event
from streambuild.executor.publish.helpers.resolution import resolve_publish_deployment_id
from streambuild.executor.publish.helpers.views import publish_stable_views
from streambuild.executor.publish.models import PublishedView, PublishRequest, PublishResult
from streambuild.integrations.clickhouse.client import ClickHouseClient


def execute_publish(request: PublishRequest, client: ClickHouseClient) -> PublishResult:
    """Publish a staged deployment by creating or replacing stable logical views."""

    resolved_deployment_id: str = resolve_publish_deployment_id(
        client=client,
        metadata_database=request.metadata_database,
        default_database=request.default_database,
        deployment_id=request.deployment_id,
    )
    published_views: tuple[PublishedView, ...] = publish_stable_views(
        client=client,
        metadata_database=request.metadata_database,
        default_database=request.default_database,
        deployment_id=resolved_deployment_id,
    )
    persist_publish_event(
        client=client,
        metadata_database=request.metadata_database,
        deployment_id=resolved_deployment_id,
        published_views=published_views,
    )
    return PublishResult(
        deployment_id=resolved_deployment_id,
        published_views=published_views,
    )
