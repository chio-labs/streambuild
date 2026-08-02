"""Build deterministically ordered metadata-state records."""

from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.planner.models import (
    DeploymentRecord,
    DeploymentWatermarkRecord,
    MetadataState,
    ObjectStateRecord,
    PreparedObjectMapping,
    PublishEventRecord,
)


def build_metadata_state(
    *,
    object_states: tuple[ObjectStateRecord, ...],
    deployments: tuple[DeploymentRecord, ...],
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...],
    publish_events: tuple[PublishEventRecord, ...],
) -> MetadataState:
    """Build deterministically ordered metadata-state records."""

    sorted_object_states: tuple[ObjectStateRecord, ...] = tuple(
        sorted(
            object_states,
            key=lambda object_state: (
                object_state.deployment_id,
                object_state.key.object_type,
                object_state.key.name,
            ),
        )
    )
    sorted_deployments: tuple[DeploymentRecord, ...] = tuple(
        sorted(
            (_normalize_deployment_record(deployment) for deployment in deployments),
            key=lambda deployment: deployment.deployment_id,
        )
    )
    sorted_deployment_watermarks: tuple[DeploymentWatermarkRecord, ...] = tuple(
        sorted(
            deployment_watermarks,
            key=lambda watermark: (
                watermark.deployment_id,
                watermark.root_key.object_type,
                watermark.root_key.name,
                watermark.boundary_key,
            ),
        )
    )
    sorted_publish_events: tuple[PublishEventRecord, ...] = tuple(
        sorted(
            (
                PublishEventRecord(
                    deployment_id=event.deployment_id,
                    published_at=event.published_at,
                    logical_view_names=tuple(sorted(event.logical_view_names)),
                    database=event.database,
                    physical_relation_names=event.physical_relation_names,
                )
                for event in publish_events
            ),
            key=lambda event: (event.published_at, event.deployment_id),
        )
    )
    return MetadataState(
        object_states=sorted_object_states,
        deployments=sorted_deployments,
        deployment_watermarks=sorted_deployment_watermarks,
        publish_events=sorted_publish_events,
    )


def _normalize_deployment_record(deployment: DeploymentRecord) -> DeploymentRecord:
    """Normalize nested deployment record ordering for deterministic state."""

    sorted_root_keys: tuple[ObjectKey, ...] = tuple(
        sorted(
            deployment.selected_root_keys,
            key=lambda root_key: (root_key.object_type, root_key.name),
        )
    )
    sorted_warning_codes: tuple[str, ...] = tuple(sorted(deployment.warning_codes))
    sorted_prepared_object_mappings: tuple[PreparedObjectMapping, ...] = tuple(
        sorted(
            deployment.prepared_object_mappings,
            key=lambda mapping: (
                mapping.logical_key.object_type,
                mapping.logical_key.name,
            ),
        )
    )
    return DeploymentRecord(
        deployment_id=deployment.deployment_id,
        created_at=deployment.created_at,
        status=deployment.status,
        replay_lineage_mode=deployment.replay_lineage_mode,
        selected_root_keys=sorted_root_keys,
        warning_codes=sorted_warning_codes,
        prepared_object_mappings=sorted_prepared_object_mappings,
        workflow_fingerprint=deployment.workflow_fingerprint,
        boundary_time=deployment.boundary_time,
        tool_version=deployment.tool_version,
    )
