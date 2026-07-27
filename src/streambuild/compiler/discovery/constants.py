"""Discovery constants."""

from __future__ import annotations

import re

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
        "replay_on_change",
        "bounded_replay_fallback",
    }
)
DEFAULT_SQL_MODEL_ENGINE: str = "MergeTree()"
DEFAULT_SQL_MODEL_ORDER_BY: tuple[str, ...] = ("_replay_timestamp",)
PROJECT_CONFIG_FILE_NAME: str = "streambuild_project.toml"
LOCAL_CONFIG_FILE_NAME: str = "streambuild_local.toml"
LEGACY_PROJECT_CONFIG_FILE_NAME: str = "streambuild_project.yml"
LEGACY_LOCAL_CONFIG_FILE_NAME: str = "streambuild_local.yml"

PIPELINE_FILE_NAME: str = "pipeline.yml"
PIPELINE_KEYS: frozenset[str] = frozenset({"source", "replay_on_change", "bounded_replay_fallback"})
DEFAULT_ADAPTER_NAME: str = "clickhouse"
PYTHON_PACKAGE_INITIALIZER_FILE_NAME: str = "__init__.py"
FULL_REPLAY_POLICY_VALUE: str = "full"
INTERPOLATION_NAMESPACE_SEPARATOR: str = ":"
INTERPOLATION_TOKEN_START: str = "${"
PROJECT_CONFIG_KEYS: frozenset[str] = frozenset(
    {"name", "adapter", "default_target", "settings", "connection", "vars", "targets", "defaults"}
)
LOCAL_CONFIG_KEYS: frozenset[str] = frozenset(
    {"target", "adapter", "settings", "connection", "vars", "targets"}
)
SETTINGS_KEYS: frozenset[str] = frozenset({"virtual_environments"})
TARGET_KEYS: frozenset[str] = frozenset({"database", "connection", "vars"})
DEFAULTS_KEYS: frozenset[str] = frozenset({"replay_on_change", "bounded_replay_fallback"})
SOURCE_FILE_KEYS: frozenset[str] = frozenset({"sources"})
SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "kind",
        "broker_list",
        "topic",
        "consumer_group",
        "format",
        "settings",
        "table_name",
        "replay_boundary",
    }
)
REPLAY_BOUNDARY_KEYS: frozenset[str] = frozenset({"mode", "columns"})
REPLAY_BOUNDARY_COLUMN_KEYS: frozenset[str] = frozenset(
    {
        "_replay_partition",
        "_replay_offset",
        "_replay_timestamp",
        "_replay_landed_at",
        "_replay_cursor",
    }
)
SECONDS_BY_DURATION_UNIT: dict[str, int] = {
    "d": 24 * 60 * 60,
    "h": 60 * 60,
    "m": 60,
    "s": 1,
}

PIPELINE_NAME_KEY: str = "name"
