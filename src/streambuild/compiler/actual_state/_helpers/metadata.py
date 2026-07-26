"""Metadata-backed actual-state helpers."""

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterRelationNotFoundError
from streambuild.clickhouse.metadata_state.constants import METADATA_OBJECT_STATE_TABLE_NAME
from streambuild.compiler.actual_state.models import ObjectStateMetadataRow
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.compiler.metadata_state.models import ObjectStateRecord


def load_object_state_records(
    *,
    client: AdapterConnection,
    metadata_database: str,
    deployment_id: str,
) -> tuple[ObjectStateRecord, ...]:
    """Load persisted object-state snapshots for one deployment."""

    records_by_deployment: dict[str, tuple[ObjectStateRecord, ...]] = (
        load_object_state_records_by_deployments(
            client=client,
            metadata_database=metadata_database,
            deployment_ids=(deployment_id,),
        )
    )
    return records_by_deployment.get(deployment_id, ())


def load_object_state_records_by_deployments(
    *,
    client: AdapterConnection,
    metadata_database: str,
    deployment_ids: tuple[str, ...],
) -> dict[str, tuple[ObjectStateRecord, ...]]:
    """Load persisted object-state snapshots for many deployments in one query."""

    if not deployment_ids:
        return {}

    try:
        rows: tuple[ObjectStateMetadataRow, ...] = client.query_many(
            statement="SELECT deployment_id, database_name, object_type, object_name, "
            "normalized_fingerprint, "
            "normalized_query, recorded_at "
            f"FROM {metadata_database}.{METADATA_OBJECT_STATE_TABLE_NAME} "
            f"WHERE deployment_id IN ({_quoted_sql_string_list(deployment_ids)})",
            decode=_decode_object_state_metadata_row,
        )
    except AdapterRelationNotFoundError:
        return {}
    records_by_deployment: dict[str, list[ObjectStateRecord]] = {
        known_deployment_id: [] for known_deployment_id in deployment_ids
    }
    row: ObjectStateMetadataRow
    for row in rows:
        records_by_deployment.setdefault(row.deployment_id, []).append(
            ObjectStateRecord(
                deployment_id=row.deployment_id,
                key=ObjectKey(
                    database=row.database_name,
                    object_type=row.object_type,
                    name=row.object_name,
                ),
                normalized_fingerprint=row.normalized_fingerprint,
                normalized_query=row.normalized_query,
                recorded_at=row.recorded_at,
            )
        )
    return {
        known_deployment_id: tuple(records)
        for known_deployment_id, records in records_by_deployment.items()
    }


def load_latest_object_state_records_by_keys(
    *,
    client: AdapterConnection,
    metadata_database: str,
    keys: tuple[ObjectKey, ...],
) -> dict[ObjectKey, ObjectStateRecord]:
    if not keys:
        return {}
    key_clauses: tuple[str, ...] = tuple(
        "(database_name "
        + ("IS NULL" if key.database is None else f"= {_quoted_sql_string(key.database)}")
        + f" AND object_type = {_quoted_sql_string(str(key.object_type))}"
        + f" AND object_name = {_quoted_sql_string(key.name)})"
        for key in keys
    )
    try:
        rows: tuple[ObjectStateMetadataRow, ...] = client.query_many(
            statement="SELECT deployment_id, database_name, object_type, object_name, "
            "normalized_fingerprint, "
            "normalized_query, recorded_at "
            f"FROM {metadata_database}.{METADATA_OBJECT_STATE_TABLE_NAME} "
            f"WHERE {' OR '.join(key_clauses)}",
            decode=_decode_object_state_metadata_row,
        )
    except AdapterRelationNotFoundError:
        return {}
    latest_records: dict[ObjectKey, ObjectStateRecord] = {}
    for row in rows:
        key: ObjectKey = ObjectKey(
            database=row.database_name,
            object_type=row.object_type,
            name=row.object_name,
        )
        record: ObjectStateRecord = ObjectStateRecord(
            deployment_id=row.deployment_id,
            key=key,
            normalized_fingerprint=row.normalized_fingerprint,
            normalized_query=row.normalized_query,
            recorded_at=row.recorded_at,
        )
        current_record: ObjectStateRecord | None = latest_records.get(key)
        if current_record is None or record.recorded_at > current_record.recorded_at:
            latest_records[key] = record
    return latest_records


def _decode_object_state_metadata_row(row: Mapping[str, object]) -> ObjectStateMetadataRow:
    return ObjectStateMetadataRow(
        deployment_id=str(row["deployment_id"]),
        database_name=None if row["database_name"] is None else str(row["database_name"]),
        object_type=DesiredObjectType(str(row["object_type"])),
        object_name=str(row["object_name"]),
        normalized_fingerprint=str(row["normalized_fingerprint"]),
        normalized_query=None if row["normalized_query"] is None else str(row["normalized_query"]),
        recorded_at=str(row["recorded_at"]),
    )


def _quoted_sql_string_list(values: tuple[str, ...]) -> str:
    return ", ".join(_quoted_sql_string(value) for value in values)


def _quoted_sql_string(value: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"
