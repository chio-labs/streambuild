"""Standard-build constants."""

from streambuild.compiler.compile.constants import (
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.discovery.types import ReplayLineageMode

SCALAR_BOUNDARY_COLUMN_BY_MODE: dict[ReplayLineageMode, str] = {
    ReplayLineageMode.TIMESTAMP: REPLAY_TIMESTAMP_COLUMN_NAME,
    ReplayLineageMode.LANDED_AT: REPLAY_LANDED_AT_COLUMN_NAME,
}
MODEL_TABLE_RELATION_INDEX: int = 0
MODEL_VIEW_RELATION_INDEX: int = 1
STANDARD_TABLE_RESOURCE_KIND: str = "table"
STANDARD_VIEW_RESOURCE_KIND: str = "materialized_view"
