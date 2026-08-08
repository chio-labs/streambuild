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
        "kind",
        "description",
        "columns",
        "audits",
        "relation_name",
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
VIEW_FORBIDDEN_MODEL_KEYS: frozenset[str] = frozenset(
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
DEFAULT_TABLE_PREFIX: str = "tbl__"
DEFAULT_VIEW_PREFIX: str = "view__"
PROJECT_CONFIG_FILE_NAME: str = "streambuild_project.toml"
LOCAL_CONFIG_FILE_NAME: str = "streambuild_local.toml"
LEGACY_PROJECT_CONFIG_FILE_NAME: str = "streambuild_project.yml"
LEGACY_LOCAL_CONFIG_FILE_NAME: str = "streambuild_local.yml"

PIPELINE_CONFIG_FILE_NAME: str = "pipeline.toml"
PIPELINE_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "mode",
        "replay_on_change",
        "bounded_replay_fallback",
        "naming",
        "protection",
        "audit_defaults",
    }
)
NAMING_KEYS: frozenset[str] = frozenset({"table_prefix", "view_prefix"})
NAMING_TABLE_PREFIX_KEY: str = "table_prefix"
NAMING_VIEW_PREFIX_KEY: str = "view_prefix"
PROTECTION_KEYS: frozenset[str] = frozenset({"warning", "confirmation"})
PROTECTION_CONFIRMATION_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
PROTECTION_CONFIRMATION_UNSAFE_PATTERN: re.Pattern[str] = re.compile(r"[^A-Za-z0-9._:-]")
DEFAULT_ADAPTER_NAME: str = "clickhouse"
PYTHON_PACKAGE_INITIALIZER_FILE_NAME: str = "__init__.py"
FULL_REPLAY_POLICY_VALUE: str = "full"
INTERPOLATION_NAMESPACE_SEPARATOR: str = ":"
INTERPOLATION_TOKEN_START: str = "${"
PROJECT_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "adapter",
        "default_target",
        "connection",
        "vars",
        "targets",
        "defaults",
        "naming",
        "audit_scheduler",
    }
)
LOCAL_CONFIG_KEYS: frozenset[str] = frozenset(
    {"target", "adapter", "defaults", "connection", "vars", "targets"}
)
TARGET_KEYS: frozenset[str] = frozenset({"database", "connection", "vars", "audit_scheduler"})
AUDIT_SCHEDULER_KEYS: frozenset[str] = frozenset({"enabled"})
DEFAULTS_KEYS: frozenset[str] = frozenset(
    {
        "managed_source_ttl",
        "model_ttl",
        "kafka_broker_list",
        "pipeline_mode",
        "replay_on_change",
        "bounded_replay_fallback",
        "freshness",
        "audits",
        "deployment_readiness",
        "sources",
    }
)
DEPLOYMENT_READINESS_KEYS: frozenset[str] = frozenset({"maximum_lag", "minimum_staged_row_ratio"})
SOURCE_DEFAULT_KEYS: frozenset[str] = frozenset({"kafka"})
KAFKA_SOURCE_DEFAULT_KEYS: frozenset[str] = frozenset({"naming_macro"})
KAFKA_NAMING_MACRO_TOPIC_PARAMETER: str = "topic"
LOCAL_DEFAULTS_KEYS: frozenset[str] = frozenset({"pipeline_mode"})
PIPELINE_MODE_KEY: str = "pipeline_mode"
SOURCE_FILE_KEYS: frozenset[str] = frozenset({"sources"})
SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "kind",
        "broker_list",
        "topic",
        "consumer_group",
        "format",
        "ttl",
        "settings",
        "table_name",
        "replay_boundary",
        "freshness",
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
FRESHNESS_KEYS: frozenset[str] = frozenset({"warn_after", "error_after"})
MODEL_COLUMN_KEYS: frozenset[str] = frozenset({"description", "audits"})
FRESHNESS_DURATION_PATTERN: re.Pattern[str] = re.compile(r"(\d+)([dhms])")
DURATION_PATTERN: re.Pattern[str] = re.compile(r"(\d+)([dhms])")
AUDIT_DEFAULT_KEYS: frozenset[str] = frozenset({"severity", "every", "warmup"})
AUDIT_SEVERITIES: frozenset[str] = frozenset({"error", "warning"})
AUDIT_DEFAULT_EVERY_KEY: str = "every"
AUDIT_DEFAULT_WARMUP_KEY: str = "warmup"
SECONDS_BY_DURATION_UNIT: dict[str, int] = {
    "d": 24 * 60 * 60,
    "h": 60 * 60,
    "m": 60,
    "s": 1,
}
