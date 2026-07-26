"""Translation of ClickHouse driver errors into neutral adapter exceptions."""

from streambuild.adapter.exceptions import (
    AdapterAuthenticationError,
    AdapterDatabaseNotFoundError,
    AdapterRelationNotFoundError,
    AdapterTimeoutError,
    AdapterWarehouseError,
)
from streambuild.adapters.clickhouse.constants import (
    AUTHENTICATION_FAILED_ERROR_CODE,
    AUTHENTICATION_FAILED_MESSAGE,
    TIMEOUT_ERROR_MARKERS,
    UNKNOWN_DATABASE_ERROR_CODE,
    UNKNOWN_TABLE_ERROR_CODE,
)


def translate_driver_error(error: Exception) -> AdapterWarehouseError:
    """Classify a ClickHouse driver error as a neutral warehouse failure."""

    error_message: str = str(error)
    normalized_error_message: str = error_message.lower()
    if any(marker in normalized_error_message for marker in TIMEOUT_ERROR_MARKERS):
        return AdapterTimeoutError(error_message)
    if (
        AUTHENTICATION_FAILED_ERROR_CODE in error_message
        or AUTHENTICATION_FAILED_MESSAGE in error_message
    ):
        return AdapterAuthenticationError(error_message)
    if UNKNOWN_DATABASE_ERROR_CODE in error_message:
        return AdapterDatabaseNotFoundError(error_message)
    if UNKNOWN_TABLE_ERROR_CODE in error_message:
        return AdapterRelationNotFoundError(error_message)
    return AdapterWarehouseError(error_message)
