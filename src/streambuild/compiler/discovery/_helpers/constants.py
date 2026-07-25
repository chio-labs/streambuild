"""Constants for pipeline discovery helpers."""

from __future__ import annotations

import re

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
