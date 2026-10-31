"""Stable authentication and account-control constants."""

from uuid import UUID

ADMIN_ROLE: str = "admin"
VIEWER_ROLE: str = "viewer"
ACCOUNT_SCHEMA_COMPONENT: str = "accounts"
CSRF_HEADER: str = "X-SQLTide-CSRF"
TRUSTED_PROXY_CSRF_PROOF: str = "trusted-proxy"
PASSWORD_MIN_LENGTH: int = 12
LOGIN_ATTEMPT_WINDOW_MINUTES: int = 1
LOGIN_USER_ATTEMPT_LIMIT: int = 5
LOGIN_IP_ATTEMPT_LIMIT: int = 20
LOGIN_LIMITER_MAX_KEYS: int = 2048
SQLITE_MEMORY_PATH: str = ":memory:"
SQLITE_MEMORY_URLS: frozenset[str] = frozenset({"sqlite://", "sqlite:///:memory:"})
LOCALHOST_NAME: str = "localhost"
CONTROL_STORE_TABLE_PREFIX: str = "sqltide_"
STREAMBUILD_CONTROL_STORE_TABLE_PREFIX: str = "streambuild_"
LOCAL_USER_ID: UUID = UUID("a25809d6-cf14-592c-b7b6-c94ef048e0cc")
PUBLIC_API_PATHS: frozenset[str] = frozenset({"/api/auth/config", "/api/auth/login"})
UNSAFE_HTTP_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
