from dataclasses import dataclass


@dataclass(frozen=True)
class BuildActualStateTestCase:
    description: str
    expected_ordered_keys: tuple[tuple[str | None, str, str], ...]
    expected_first_table_settings: dict[str, str] | None
    expected_first_mv_source_table_name: str
    expected_first_kafka_consumer_group: str
