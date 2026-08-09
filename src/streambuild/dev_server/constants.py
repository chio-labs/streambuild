"""Dev server constants."""

DEFAULT_DEV_SERVER_HOST: str = "127.0.0.1"
DEFAULT_DEV_SERVER_PORT: int = 8000
REDACTED_SECRET_PLACEHOLDER: str = "<redacted>"
BROKER_USERINFO_SEPARATOR: str = "@"
KAFKA_SECURITY_PROTOCOL_CONFIG_NAME: str = "security_protocol"
SENSITIVE_SOURCE_SETTING_FRAGMENTS: tuple[str, ...] = (
    "credential",
    "password",
    "private_key",
    "sasl",
    "secret",
    "token",
)
STATIC_ASSETS_DIRECTORY_NAME: str = "static"
IDENTITY_DRIFT_STATUSES: frozenset[str] = frozenset(
    {"binding_changed", "definition_changed", "execution_changed"}
)
CANCEL_GRACE_SECONDS: float = 15.0
TERMINATE_GRACE_SECONDS: float = 3.0
THROUGHPUT_WINDOW_LADDER: tuple[tuple[int, int], ...] = (
    (3600, 60),
    (86400, 1800),
    (604800, 10800),
)
