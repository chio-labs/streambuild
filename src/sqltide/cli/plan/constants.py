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
CLICKHOUSE_INTEGER_TYPES: frozenset[str] = frozenset(
    {
        "Int8",
        "Int16",
        "Int32",
        "Int64",
        "Int128",
        "Int256",
        "UInt8",
        "UInt16",
        "UInt32",
        "UInt64",
        "UInt128",
        "UInt256",
    }
)
CLICKHOUSE_DATETIME_TYPES: frozenset[str] = frozenset({"DateTime", "DateTime64"})
CLICKHOUSE_DATETIME_PREFIXES: tuple[str, ...] = ("DateTime(", "DateTime64(")
CLICKHOUSE_SCALAR_TYPE_WRAPPERS: tuple[str, ...] = ("Nullable", "LowCardinality")
DIRECT_MODE_LABEL: str = "direct"
VIRTUAL_ENVIRONMENTS_MODE_LABEL: str = "virtual environments"
