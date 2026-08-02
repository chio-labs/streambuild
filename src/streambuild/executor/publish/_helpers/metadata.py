"""Metadata state assembly for publish execution."""

from streambuild.adapter.models import AdapterMetadataState
from streambuild.compiler.planner.main.build_adapter_metadata_state import (
    build_adapter_metadata_state,
)
from streambuild.compiler.planner.main.build_metadata_state import build_metadata_state
from streambuild.compiler.planner.models import MetadataState, PublishEventRecord
from streambuild.executor.publish.models import PublishedView


def build_publish_metadata_state(
    *,
    deployment_id: str,
    published_at: str,
    published_views: tuple[PublishedView, ...],
) -> AdapterMetadataState:
    """Build one publish history metadata batch for a deployment."""

    metadata_state: MetadataState = build_metadata_state(
        object_states=(),
        deployments=(),
        deployment_watermarks=(),
        deployment_runtime_details=(),
        publish_events=(
            PublishEventRecord(
                deployment_id=deployment_id,
                published_at=published_at,
                logical_view_names=tuple(view.view_name for view in published_views),
            ),
        ),
    )
    return build_adapter_metadata_state(metadata_state)
