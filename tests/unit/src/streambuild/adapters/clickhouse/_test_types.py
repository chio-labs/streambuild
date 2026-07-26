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
