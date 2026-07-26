"""Compile-specific constants."""

from streambuild.compiler.shared.constants import (
    KAFKA_LANDED_AT_COLUMN_NAME,
    KAFKA_OFFSET_COLUMN_NAME,
    KAFKA_PARTITION_COLUMN_NAME,
    KAFKA_TIMESTAMP_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.shared.models import Column

RAW_LANDING_COLUMNS: tuple[Column, ...] = (
    Column(name="kafka_key", type="String"),
    Column(name="kafka_value", type="String"),
    Column(name="kafka_topic", type="String"),
    Column(name=KAFKA_PARTITION_COLUMN_NAME, type="Int32"),
    Column(name=KAFKA_OFFSET_COLUMN_NAME, type="Int64"),
    Column(name=KAFKA_TIMESTAMP_COLUMN_NAME, type="Nullable(DateTime64(3))"),
    Column(name=REPLAY_PARTITION_COLUMN_NAME, type="Int32"),
    Column(name=REPLAY_OFFSET_COLUMN_NAME, type="Int64"),
    Column(name=REPLAY_TIMESTAMP_COLUMN_NAME, type="Nullable(DateTime64(3))"),
    Column(name="kafka_headers", type="String"),
    Column(name=KAFKA_LANDED_AT_COLUMN_NAME, type="DateTime64(3)"),
    Column(name=REPLAY_LANDED_AT_COLUMN_NAME, type="DateTime64(3)"),
)

AGGREGATING_ENGINE_NAMES: tuple[str, ...] = ("summingmergetree", "aggregatingmergetree")
