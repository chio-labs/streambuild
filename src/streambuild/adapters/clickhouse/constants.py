"""ClickHouse adapter constants."""

from streambuild.adapter.constants import MANAGED_SOURCE_KIND_KAFKA
from streambuild.adapter.types import AdapterReplayBoundaryMode

CLICKHOUSE_ADAPTER_NAME: str = "clickhouse"
CLICKHOUSE_DEFAULT_DATABASE: str = "default"
CLICKHOUSE_SQL_ANALYSIS_DIALECT: str = "clickhouse"
CLICKHOUSE_CONNECTION_CONFIG_KEYS: frozenset[str] = frozenset(
    {"host", "port", "username", "password"}
)
UNKNOWN_TABLE_ERROR_CODE: str = "UNKNOWN_TABLE"
UNKNOWN_DATABASE_ERROR_CODE: str = "UNKNOWN_DATABASE"
AUTHENTICATION_FAILED_ERROR_CODE: str = "AUTHENTICATION_FAILED"
AUTHENTICATION_FAILED_MESSAGE: str = "Authentication failed"
TIMEOUT_ERROR_MARKERS: tuple[str, ...] = ("timeout", "timed out")
CLICKHOUSE_VIRTUAL_ENVIRONMENTS_SUPPORTED: bool = True
CLICKHOUSE_MANAGED_SOURCE_KINDS: frozenset[str] = frozenset({MANAGED_SOURCE_KIND_KAFKA})
CLICKHOUSE_REPLAY_BOUNDARY_MODES: frozenset[AdapterReplayBoundaryMode] = frozenset(
    AdapterReplayBoundaryMode
)
CLICKHOUSE_HISTORY_PREFIX_SEED_SUPPORTED: bool = True
CLICKHOUSE_STABLE_LOGICAL_BINDINGS_SUPPORTED: bool = True
CLICKHOUSE_PER_RELATION_ATOMIC_REPLACE: bool = True
CLICKHOUSE_GRAPH_ATOMIC_PUBLISH: bool = False
CLICKHOUSE_VIEW_ENGINE: str = "View"
CLICKHOUSE_KAFKA_TABLE_NAME_PREFIX: str = "kafka__"
CLICKHOUSE_RAW_TABLE_NAME_PREFIX: str = "raw__"
CLICKHOUSE_MODEL_TABLE_NAME_PREFIX: str = "tbl__"
CLICKHOUSE_MATERIALIZED_VIEW_NAME_PREFIX: str = "mv__"
CLICKHOUSE_SUPPORTED_KAFKA_FORMAT: str = "JSONAsString"
CLICKHOUSE_FRAMEWORK_KAFKA_SETTING_KEYS: frozenset[str] = frozenset(
    {"kafka_broker_list", "kafka_topic_list", "kafka_group_name", "kafka_format"}
)
EMPTY_KEY_EXPRESSIONS: tuple[str, ...] = ("", "tuple()")
EMPTY_DEFAULT_EXPRESSIONS: tuple[object, ...] = (None, "")
