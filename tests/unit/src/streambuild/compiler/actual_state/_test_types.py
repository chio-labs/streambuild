from dataclasses import dataclass


@dataclass(frozen=True)
class BuildActualStateTestCase:
    description: str
    expected_ordered_keys: tuple[tuple[str | None, str, str], ...]
    expected_first_table_settings: dict[str, str] | None
    expected_first_mv_source_table_name: str
    expected_first_kafka_consumer_group: str


@dataclass(frozen=True)
class ActualStateRowNormalizationTestCase:
    description: str
    raw_engine: str
    raw_sorting_key: str
    raw_default_expression: object
    raw_partition_key: object
    expected_engine: str
    expected_order_by: tuple[str, ...]
    expected_default_expression: str | None
    expected_partition_key: str | None


@dataclass(frozen=True)
class ActualStateProjectionTestCase:
    description: str
    expected_kafka_columns: tuple[tuple[str, str, str | None], ...]
    expected_kafka_broker_list: str
    expected_kafka_topic: str
    expected_kafka_consumer_group: str
    expected_kafka_format: str
    expected_kafka_settings: dict[str, str] | None
    expected_raw_columns: tuple[tuple[str, str, str | None], ...]
    expected_raw_engine: str
    expected_raw_order_by: tuple[str, ...]
    expected_raw_partition_by: str | None
    expected_raw_ttl: str | None
    expected_raw_settings: dict[str, str] | None
    expected_landing_mv_source: str
    expected_landing_mv_target: str
    expected_landing_mv_query: str
    expected_transform_columns: tuple[tuple[str, str, str | None], ...]
    expected_transform_engine: str
    expected_transform_order_by: tuple[str, ...]
    expected_transform_partition_by: str | None
    expected_transform_ttl: str | None
    expected_transform_settings: dict[str, str] | None
