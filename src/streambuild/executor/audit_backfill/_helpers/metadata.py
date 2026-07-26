"""Deployment metadata loading for audit backfill."""

from __future__ import annotations

from collections.abc import Mapping

from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.executor.audit_backfill.models import DeploymentMetadataRow
from streambuild.spec.types import ReplayLineageMode


def _object_key_from_payload(payload: dict[str, object]) -> ObjectKey:
    return ObjectKey(
        database=str(payload["database"]) if payload["database"] is not None else None,
        object_type=DesiredObjectType(str(payload["object_type"])),
        name=str(payload["name"]),
    )


def _decode_deployment_metadata_row(row: Mapping[str, object]) -> DeploymentMetadataRow:
    return DeploymentMetadataRow(
        created_at=str(row["created_at"]),
        status=str(row["status"]),
        replay_lineage_mode=ReplayLineageMode(str(row["replay_lineage_mode"])),
        selected_root_keys_json=str(row["selected_root_keys_json"]),
        warning_codes_json=str(row["warning_codes_json"]),
        prepared_object_mappings_json=str(row["prepared_object_mappings_json"]),
    )
