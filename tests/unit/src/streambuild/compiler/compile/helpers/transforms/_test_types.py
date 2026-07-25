from dataclasses import dataclass


@dataclass(frozen=True)
class CompileTransformTableTestCase:
    description: str
    expected_table_name: str
    expected_table_key: tuple[str | None, str, str]
    expected_dep_keys: tuple[tuple[str | None, str, str], ...]
    expected_column_names: tuple[str, ...]
    expected_column_types: tuple[str, ...]
    expected_engine: str
    expected_order_by: tuple[str, ...]
    expected_partition_by: str
    expected_ttl: str
    expected_settings: dict[str, str]
