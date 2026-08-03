"""Dev server constants."""

DEFAULT_DEV_SERVER_HOST: str = "127.0.0.1"
DEFAULT_DEV_SERVER_PORT: int = 8000
REDACTED_SECRET_PLACEHOLDER: str = "<redacted>"
BROKER_USERINFO_SEPARATOR: str = "@"
SENSITIVE_SOURCE_SETTING_FRAGMENTS: tuple[str, ...] = (
    "credential",
    "password",
    "private_key",
    "sasl",
    "secret",
    "token",
)
