"""Path and module constants for StreamBuild's Fensu policy."""

PRODUCT_SCOPE_NAME: str = "root"
COMPILER_PATH_PREFIX: tuple[str, ...] = ("src", "streambuild", "compiler")
SQL_ANALYSIS_PATH_PREFIX: tuple[str, ...] = (
    "src",
    "streambuild",
    "compiler",
    "sql_analysis",
)
CLICKHOUSE_ADAPTER_PATH_PREFIX: tuple[str, ...] = (
    "src",
    "streambuild",
    "adapters",
    "clickhouse",
)
ADAPTER_IMPLEMENTATION_MODULE_PREFIX: tuple[str, ...] = ("streambuild", "adapters")
CLICKHOUSE_DRIVER_ROOT_MODULE: str = "clickhouse_connect"
POLYGLOT_ROOT_MODULE: str = "polyglot_sql"
SQLGLOT_ROOT_MODULE: str = "sqlglot"
DYNAMIC_IMPORT_CALL_NAMES: tuple[str, ...] = ("__import__", "importlib.import_module")
RETIRED_CLICKHOUSE_MODULE_PREFIX: tuple[str, ...] = ("streambuild", "clickhouse")
RETIRED_CLICKHOUSE_INTEGRATION_MODULE_PREFIX: tuple[str, ...] = (
    "streambuild",
    "integrations",
    "clickhouse",
)
