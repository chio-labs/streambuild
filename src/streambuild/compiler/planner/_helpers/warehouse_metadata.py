"""Load persisted object state into one planning warehouse snapshot."""

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import METADATA_OBJECT_STATE_TABLE_NAME
from streambuild.adapter.exceptions import AdapterRelationNotFoundError
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.compiler.metadata_state.models import ObjectStateRecord
from streambuild.compiler.planner.models import ObjectStateMetadataRow


def load_all_object_state_records(
    *,
    client: AdapterConnection,
    metadata_database: str,
) -> tuple[ObjectStateRecord, ...]:
    """Load every persisted object-state row into one planning snapshot."""

    try:
        rows: tuple[ObjectStateMetadataRow, ...] = client.query_many(
            statement="SELECT deployment_id, database_name, object_type, object_name, "
            "normalized_fingerprint, normalized_query, recorded_at "
            f"FROM {metadata_database}.{METADATA_OBJECT_STATE_TABLE_NAME}",
            decode=_decode_object_state_metadata_row,
        )
    except AdapterRelationNotFoundError:
        return ()
    return tuple(
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
        for row in rows
    )


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
