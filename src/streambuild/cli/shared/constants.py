"""Shared CLI presentation constants for commands under main/."""

ANSI_RESET: str = "\033[0m"
ANSI_BOLD: str = "\033[1m"
ANSI_DIM: str = "\033[2m"
ANSI_BLUE: str = "\033[34m"
ANSI_GREEN: str = "\033[32m"
ANSI_YELLOW: str = "\033[33m"
ANSI_RED: str = "\033[31m"

AFFIRMATIVE_RESPONSES: frozenset[str] = frozenset({"y", "yes"})
TRUTHY_ENV_VALUES: frozenset[str] = frozenset({"1", "true", "yes"})

NOT_AVAILABLE: str = "n/a"
UTC_SUFFIX: str = "Z"

UPSTREAM_SELECTOR_PREFIX: str = "+"
SELECTOR_NAMESPACE_SEPARATOR: str = ":"
PIPELINE_SELECTOR_NAMESPACE: str = "pipeline"

DATE_ONLY_START_TIME_FORMAT: str = "%Y-%m-%d"
ACCEPTED_START_TIME_FORMATS: tuple[str, ...] = (
    DATE_ONLY_START_TIME_FORMAT,
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
)
START_OF_DAY_CLICKHOUSE_FORMAT: str = "%Y-%m-%d 00:00:00.000"
CLICKHOUSE_TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M:%S.%f"

UNKNOWN_DATABASE_ERROR_MARKER: str = "UNKNOWN_DATABASE"
METADATA_TABLE_NAME_PREFIX: str = "streambuild_"
DATETIME_TYPE_MARKER: str = "datetime"
