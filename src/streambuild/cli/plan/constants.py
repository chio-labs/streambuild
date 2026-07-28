"""CLI plan constants."""

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
DATETIME_TYPE_MARKER: str = "datetime"
STANDARD_MODE_LABEL: str = "standard"
VIRTUAL_ENVIRONMENTS_MODE_LABEL: str = "virtual environments"
