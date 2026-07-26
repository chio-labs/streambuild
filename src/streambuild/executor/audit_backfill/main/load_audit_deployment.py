"""Load the deployment record audited by a backfill readiness check."""

from __future__ import annotations

import json

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterRelationNotFoundError
from streambuild.executor.audit_backfill._helpers.metadata import (
    _decode_deployment_metadata_row,
    _object_key_from_payload,
)
from streambuild.executor.audit_backfill.models import DeploymentMetadataRow, LoadedAuditDeployment


def load_audit_deployment(
    *,
    client: AdapterConnection,
    metadata_database: str,
    deployment_id: str,
) -> LoadedAuditDeployment:
    """Load the persisted deployment metadata needed for audit."""

    try:
        row: DeploymentMetadataRow | None = client.query_one(
            statement="SELECT created_at, status, replay_lineage_mode, selected_root_keys_json, "
            "warning_codes_json, prepared_object_mappings_json "
            f"FROM {metadata_database}.streambuild_deployments "
            f"WHERE deployment_id = '{deployment_id}'",
            decode=_decode_deployment_metadata_row,
        )
    except AdapterRelationNotFoundError:
        return LoadedAuditDeployment(
            deployment_id=deployment_id,
            created_at="",
            status="metadata_missing",
            replay_lineage_mode=None,
            warning_codes=(),
            root_keys=(),
            prepared_object_mappings=(),
        )
    if row is None:
        return LoadedAuditDeployment(
            deployment_id=deployment_id,
            created_at="",
            status="metadata_missing",
            replay_lineage_mode=None,
            warning_codes=(),
            root_keys=(),
            prepared_object_mappings=(),
        )

    root_keys_payload: list[dict[str, object]] = json.loads(row.selected_root_keys_json)
    warning_codes_payload: list[str] = json.loads(row.warning_codes_json)
    prepared_mappings_payload: list[dict[str, object]] = json.loads(
        row.prepared_object_mappings_json
    )
    return LoadedAuditDeployment(
        deployment_id=deployment_id,
        created_at=row.created_at,
        status=row.status,
        replay_lineage_mode=row.replay_lineage_mode,
        warning_codes=tuple(warning_codes_payload),
        root_keys=tuple(_object_key_from_payload(payload) for payload in root_keys_payload),
        prepared_object_mappings=tuple(
            (
                _object_key_from_payload(mapping_payload["logical_key"]),
                str(mapping_payload["physical_name"]),
            )
            for mapping_payload in prepared_mappings_payload
        ),
    )
