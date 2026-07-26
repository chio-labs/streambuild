"""Metadata loading helpers for janitor execution."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError

from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.metadata_state.models import DeploymentRecord, PreparedObjectMapping
from streambuild.executor.janitor.models import DeploymentMetadataRow, PublishHistoryMetadataRow
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.constants import UNKNOWN_TABLE_ERROR_CODE


def load_deployments(
    *, client: ClickHouseClient, metadata_database: str
) -> tuple[DeploymentRecord, ...]:
    rows: tuple[DeploymentMetadataRow, ...] = client.query_many(
        statement="SELECT deployment_id, created_at, status, replay_lineage_mode, "
        "selected_root_keys_json, warning_codes_json, prepared_object_mappings_json "
        f"FROM {metadata_database}.streambuild_deployments",
        decode=_decode_deployment_metadata_row,
    )
    records: list[DeploymentRecord] = []
    row: DeploymentMetadataRow
    for row in rows:
        prepared_payload: list[dict[str, object]] = json.loads(row.prepared_object_mappings_json)
        records.append(
            DeploymentRecord(
                deployment_id=row.deployment_id,
                created_at=row.created_at,
                status=row.status,
                replay_lineage_mode=row.replay_lineage_mode,
                selected_root_keys=(),
                warning_codes=(),
                prepared_object_mappings=tuple(
                    PreparedObjectMapping(
                        logical_key=ObjectKey(
                            database=(
                                None
                                if mapping["logical_key"]["database"] is None
                                else str(mapping["logical_key"]["database"])
                            ),
                            object_type=DesiredObjectType(
                                str(mapping["logical_key"]["object_type"])
                            ),
                            name=str(mapping["logical_key"]["name"]),
                        ),
                        physical_name=str(mapping["physical_name"]),
                    )
                    for mapping in prepared_payload
                ),
            )
        )
    return tuple(records)


def load_latest_publish_times(
    *,
    client: ClickHouseClient,
    metadata_database: str,
) -> dict[str, datetime]:
    try:
        rows: tuple[PublishHistoryMetadataRow, ...] = client.query_many(
            statement="SELECT deployment_id, max(published_at) AS latest_published_at "
            f"FROM {metadata_database}.streambuild_publish_history GROUP BY deployment_id",
            decode=_decode_publish_history_metadata_row,
        )
    except (DatabaseError, OperationalError) as error:
        if UNKNOWN_TABLE_ERROR_CODE in str(error):
            return {}
        raise
    latest_publish_times: dict[str, datetime] = {}
    row: PublishHistoryMetadataRow
    for row in rows:
        latest_publish_times[row.deployment_id] = _parse_clickhouse_time(row.latest_published_at)
    return latest_publish_times


def _parse_clickhouse_time(value: str) -> datetime:
    normalized: str = value.replace(" ", "T")
    return datetime.fromisoformat(normalized).replace(tzinfo=UTC)


def _decode_deployment_metadata_row(row: Mapping[str, object]) -> DeploymentMetadataRow:
    return DeploymentMetadataRow(
        deployment_id=str(row["deployment_id"]),
        created_at=str(row["created_at"]),
        status=str(row["status"]),
        replay_lineage_mode=ReplayLineageMode(str(row["replay_lineage_mode"])),
        prepared_object_mappings_json=str(row["prepared_object_mappings_json"]),
    )


def _decode_publish_history_metadata_row(
    row: Mapping[str, object],
) -> PublishHistoryMetadataRow:
    return PublishHistoryMetadataRow(
        deployment_id=str(row["deployment_id"]),
        latest_published_at=str(row["latest_published_at"]),
    )
