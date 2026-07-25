from dataclasses import dataclass


@dataclass(frozen=True)
class CompileKafkaLandingTestCase:
    description: str
    expected_kafka_table_name: str
    expected_kafka_table_key: tuple[str | None, str, str]
    expected_kafka_column_names: tuple[str, ...]
    expected_kafka_broker_list: str
    expected_topic: str
    expected_consumer_group: str
    expected_format: str
    expected_kafka_extra_settings: dict[str, str] | None
    expected_raw_table_name: str
    expected_raw_table_key: tuple[str | None, str, str]
    expected_raw_column_names: tuple[str, ...]
    expected_raw_engine: str
    expected_raw_order_by: tuple[str, ...]
    expected_mv_name: str
    expected_mv_key: tuple[str | None, str, str]
    expected_mv_dep_keys: tuple[tuple[str | None, str, str], ...]
    expected_mv_source_table_name: str
    expected_mv_target_table_name: str
    expected_mv_query_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompileKafkaLandingErrorTestCase:
    description: str
    source_format: str | None
    consumer_group: str | None
    settings: dict[str, str] | None
    expected_error_type: type[Exception]
    expected_error_fragment: str
