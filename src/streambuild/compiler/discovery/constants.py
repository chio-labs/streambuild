"""Discovery constants."""

from __future__ import annotations

import re

CLICKHOUSE_CONNECTION_KEYS: frozenset[str] = frozenset({"host", "port", "username", "password"})
SCHEMA_CHANGE_RULE_KEYS: frozenset[str] = frozenset({"breaking", "non_breaking"})

MODEL_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*MODEL\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)$",
    re.DOTALL,
)
ALLOWED_MODEL_KEYS: frozenset[str] = frozenset(
    {
        "engine",
        "order_by",
        "partition_by",
        "ttl",
        "settings",
        "replay_anchor",
        "schema_change_backfill",
        "bounded_replay_fallback",
    }
)
DEFAULT_SQL_MODEL_ENGINE: str = "MergeTree()"
DEFAULT_SQL_MODEL_ORDER_BY: tuple[str, ...] = ("_replay_timestamp",)
PROJECT_FILE_NAME: str = "streambuild_project.yml"

PIPELINE_FILE_NAME: str = "pipeline.yml"
ALLOWED_PROJECT_KEYS: frozenset[str] = frozenset(
    {
        "version",
        "adapter",
        "default_database",
        "replay_lineage_mode",
        "bounded_replay_fallback",
        "clickhouse",
    }
)
SUPPORTED_PROJECT_VERSION: int = 2
DEFAULT_ADAPTER_NAME: str = "clickhouse"
SECONDS_BY_DURATION_UNIT: dict[str, int] = {
    "d": 24 * 60 * 60,
    "h": 60 * 60,
    "m": 60,
    "s": 1,
}

PIPELINE_NAME_KEY: str = "name"
QUALIFIED_NAME_SEPARATOR: str = "."
