"""Row serialization helpers for metadata-state inserts."""

import json

from streambuild.compiler.metadata_state.models import (
    DeploymentRecord,
    DeploymentRuntimeDetailRecord,
    DeploymentWatermarkRecord,
    ObjectStateRecord,
    PreparedObjectMapping,
    PublishEventRecord,
)
from streambuild.compiler.shared.models import ObjectKey


def build_object_state_row(record: ObjectStateRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "database_name": record.key.database,
        "object_type": record.key.object_type,
        "object_name": record.key.name,
        "normalized_fingerprint": record.normalized_fingerprint,
        "normalized_query": record.normalized_query,
        "recorded_at": record.recorded_at,
    }


def build_deployment_row(record: DeploymentRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "created_at": record.created_at,
        "status": record.status,
        "replay_lineage_mode": record.replay_lineage_mode,
        "selected_root_keys_json": json.dumps(
            [_object_key_payload(key) for key in record.selected_root_keys]
        ),
        "warning_codes_json": json.dumps(list(record.warning_codes)),
        "prepared_object_mappings_json": json.dumps(
            [
                _prepared_object_mapping_payload(mapping)
                for mapping in record.prepared_object_mappings
            ]
        ),
    }


def build_deployment_watermark_row(record: DeploymentWatermarkRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "root_database_name": record.root_key.database,
        "root_object_type": record.root_key.object_type,
        "root_object_name": record.root_key.name,
        "anchor_database_name": record.anchor_key.database,
        "anchor_object_type": record.anchor_key.object_type,
        "anchor_object_name": record.anchor_key.name,
        "boundary_key": record.boundary_key,
        "cutoff_value": record.cutoff_value,
    }


def build_deployment_runtime_detail_row(record: DeploymentRuntimeDetailRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "root_database_name": record.root_key.database,
        "root_object_type": record.root_key.object_type,
        "root_object_name": record.root_key.name,
        "state_kind": record.state_kind,
        "replay_strategy": record.replay_strategy,
        "active_deployment_id": record.active_deployment_id,
        "anchor_database_name": record.anchor_key.database,
        "anchor_object_type": record.anchor_key.object_type,
        "anchor_object_name": record.anchor_key.name,
        "anchor_physical_name": record.anchor_physical_name,
        "execution_mode": record.execution_mode,
        "configured_backfill_mode": record.configured_backfill_mode,
        "execution_lookback_seconds": record.execution_lookback_seconds,
        "live_target_names_json": json.dumps(list(record.live_target_names)),
    }


def build_publish_event_row(record: PublishEventRecord) -> dict[str, object]:
    return {
        "deployment_id": record.deployment_id,
        "published_at": record.published_at,
        "logical_view_names_json": json.dumps(list(record.logical_view_names)),
    }


def _object_key_payload(key: ObjectKey) -> dict[str, object]:
    return {
        "database": key.database,
        "object_type": key.object_type,
        "name": key.name,
    }


def _prepared_object_mapping_payload(mapping: PreparedObjectMapping) -> dict[str, object]:
    return {
        "logical_key": {
            "database": mapping.logical_key.database,
            "object_type": mapping.logical_key.object_type,
            "name": mapping.logical_key.name,
        },
        "physical_name": mapping.physical_name,
    }
