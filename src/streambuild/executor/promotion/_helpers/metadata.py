"""Metadata state assembly for publish execution."""

from hashlib import sha256
from time import time_ns

from streambuild.adapter.models import (
    AdapterMetadataState,
    AdapterPublishEventRecord,
    AdapterStableBinding,
)
from streambuild.executor.promotion.models import PublishedView


def build_publish_metadata_state(
    *,
    deployment_id: str,
    published_at: str,
    published_views: tuple[PublishedView, ...],
    database: str,
    operation: str = "promote",
    previous_deployment_id: str | None = None,
) -> AdapterMetadataState:
    """Build one publish history metadata batch for a deployment."""

    publication_id: str = (
        f"{time_ns():020d}_"
        + sha256(f"{deployment_id}:{published_at}:{operation}".encode()).hexdigest()
    )
    return AdapterMetadataState(
        object_states=(),
        deployments=(),
        deployment_watermarks=(),
        publish_events=(
            AdapterPublishEventRecord(
                deployment_id=deployment_id,
                published_at=published_at,
                logical_view_names=tuple(view.view_name for view in published_views),
                publication_id=publication_id,
                bindings=tuple(
                    AdapterStableBinding(
                        database=database,
                        logical_name=view.view_name,
                        physical_name=view.target_table_name,
                    )
                    for view in published_views
                ),
                operation=operation,
                previous_deployment_id=previous_deployment_id,
            ),
        ),
    )
