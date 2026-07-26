"""Path and module constants for StreamBuild's Fensu policy."""

PRODUCT_SCOPE_NAME: str = "root"
COMPILER_PATH_PREFIX: tuple[str, ...] = ("src", "streambuild", "compiler")
CLICKHOUSE_ADAPTER_PATH_PREFIX: tuple[str, ...] = (
    "src",
    "streambuild",
    "adapters",
    "clickhouse",
)
ADAPTER_IMPLEMENTATION_MODULE_PREFIX: tuple[str, ...] = ("streambuild", "adapters")
CLICKHOUSE_DRIVER_ROOT_MODULE: str = "clickhouse_connect"
