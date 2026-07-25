"""Shared compiler constants."""

from streambuild.compiler.shared.types import DesiredObjectType

DESIRED_OBJECT_TYPE_KAFKA_TABLE: DesiredObjectType = DesiredObjectType(
    DesiredObjectType.KAFKA_TABLE
)
DESIRED_OBJECT_TYPE_TABLE: DesiredObjectType = DesiredObjectType(DesiredObjectType.TABLE)
DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW: DesiredObjectType = DesiredObjectType(
    DesiredObjectType.MATERIALIZED_VIEW
)

KAFKA_TABLE_NAME_PREFIX: str = "kafka__"
RAW_TABLE_NAME_PREFIX: str = "raw__"
TRANSFORM_TABLE_NAME_PREFIX: str = "tbl__"
MATERIALIZED_VIEW_NAME_PREFIX: str = "mv__"

KAFKA_PARTITION_COLUMN_NAME: str = "kafka_partition"
KAFKA_OFFSET_COLUMN_NAME: str = "kafka_offset"
KAFKA_TIMESTAMP_COLUMN_NAME: str = "kafka_timestamp"
KAFKA_LANDED_AT_COLUMN_NAME: str = "kafka_landed_at"

REPLAY_PARTITION_COLUMN_NAME: str = "_replay_partition"
REPLAY_OFFSET_COLUMN_NAME: str = "_replay_offset"
REPLAY_TIMESTAMP_COLUMN_NAME: str = "_replay_timestamp"
REPLAY_LANDED_AT_COLUMN_NAME: str = "_replay_landed_at"
REPLAY_CURSOR_COLUMN_NAME: str = "_replay_cursor"

REPLAY_OFFSET_LINEAGE_COLUMN_NAMES: tuple[str, str] = (
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
)
REPLAY_TIME_LINEAGE_COLUMN_NAMES: tuple[str, str] = (
    REPLAY_TIMESTAMP_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
)
REPLAY_ALL_COLUMN_NAMES: tuple[str, str, str, str, str] = (
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_CURSOR_COLUMN_NAME,
)
REPLAY_REQUIRED_COLUMN_NAMES_BY_MODE: dict[str, tuple[str, ...]] = {
    "offsets": REPLAY_OFFSET_LINEAGE_COLUMN_NAMES,
    "timestamp": (REPLAY_TIMESTAMP_COLUMN_NAME,),
    "landed_at": (REPLAY_LANDED_AT_COLUMN_NAME,),
    "cursor": (REPLAY_CURSOR_COLUMN_NAME,),
}
