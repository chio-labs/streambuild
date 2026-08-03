"""Metadata state assembly for publish execution."""

from streambuild.adapter.models import (
    AdapterMetadataState,
    AdapterPublishEventRecord,
    AdapterStableBinding,
)
from streambuild.executor.publish.models import PublishedView


def build_publish_metadata_state(
    *,
    deployment_id: str,
    published_at: str,
    published_views: tuple[PublishedView, ...],
    database: str,
) -> AdapterMetadataState:
    """Build one publish history metadata batch for a deployment."""

    return AdapterMetadataState(
        object_states=(),
        deployments=(),
        deployment_watermarks=(),
        publish_events=(
            AdapterPublishEventRecord(
                deployment_id=deployment_id,
                published_at=published_at,
                logical_view_names=tuple(view.view_name for view in published_views),
                bindings=tuple(
                    AdapterStableBinding(
                        database=database,
                        logical_name=view.view_name,
                        physical_name=view.target_table_name,
                    )
                    for view in published_views
                ),
            ),
        ),
    )
