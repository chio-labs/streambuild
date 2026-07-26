"""ClickHouse adapter constants."""

from streambuild.adapter.constants import MANAGED_SOURCE_KIND_KAFKA
from streambuild.adapter.types import AdapterReplayBoundaryMode

CLICKHOUSE_ADAPTER_NAME: str = "clickhouse"
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
CLICKHOUSE_VIEW_ENGINE: str = "View"
EMPTY_KEY_EXPRESSIONS: tuple[str, ...] = ("", "tuple()")
EMPTY_DEFAULT_EXPRESSIONS: tuple[object, ...] = (None, "")
