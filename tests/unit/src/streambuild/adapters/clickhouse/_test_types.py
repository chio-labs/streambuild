from dataclasses import dataclass

from streambuild.adapter.exceptions import AdapterWarehouseError


@dataclass(frozen=True)
class DriverErrorTranslationTestCase:
    description: str
    driver_error: Exception
    expected_error_type: type[AdapterWarehouseError]
    expected_message: str


@dataclass(frozen=True)
class ConnectionTranslationTestCase:
    description: str
    driver_error: Exception
    expected_error_type: type[AdapterWarehouseError]


@dataclass(frozen=True)
class ConnectionQueryNormalizationTestCase:
    description: str
    raw_column_names: list[str]
    raw_result_rows: list[list[object]]
    expected_column_names: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class CatalogInspectionTestCase:
    description: str
    expected_timezone: str
    expected_relation_names: frozenset[str]
    expected_query_count: int


@dataclass(frozen=True)
class BuildInspectedManagedTableStateTestCase:
    description: str
    system_rows: tuple[tuple[str, str], ...]
    expected_logical_names: tuple[str, ...]
