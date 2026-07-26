"""Discovery constants."""

CLICKHOUSE_CONNECTION_KEYS: frozenset[str] = frozenset({"host", "port", "username", "password"})
SCHEMA_CHANGE_RULE_KEYS: frozenset[str] = frozenset({"breaking", "non_breaking"})
