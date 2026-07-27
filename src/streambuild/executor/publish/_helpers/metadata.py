"""Metadata persistence for publish execution."""

from datetime import UTC, datetime

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.planner.main.build_adapter_metadata_state import (
    build_adapter_metadata_state,
)
from streambuild.compiler.planner.main.build_metadata_state import build_metadata_state
from streambuild.compiler.planner.models import MetadataState, PublishEventRecord
from streambuild.executor.backfill.main._ensure_metadata_tables import ensure_metadata_tables
from streambuild.executor.publish.models import PublishedView


def persist_publish_event(
    *,
    client: AdapterConnection,
    metadata_database: str,
    deployment_id: str,
    published_views: tuple[PublishedView, ...],
) -> None:
    """Persist one publish history event for a deployment."""

    ensure_metadata_tables(client=client, metadata_database=metadata_database)
    published_at: str = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
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
    client.persist_metadata_state(
        database=metadata_database,
        state=build_adapter_metadata_state(metadata_state),
    )
