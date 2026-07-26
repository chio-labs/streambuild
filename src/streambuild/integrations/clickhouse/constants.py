"""ClickHouse driver constants."""

UNKNOWN_TABLE_ERROR_CODE: str = "UNKNOWN_TABLE"
AUTHENTICATION_FAILED_ERROR_CODE: str = "AUTHENTICATION_FAILED"
AUTHENTICATION_FAILED_MESSAGE: str = "Authentication failed"
EMPTY_TUPLE_EXPRESSION: str = "tuple()"
BLANK_VALUES: tuple[object, ...] = (None, "")
