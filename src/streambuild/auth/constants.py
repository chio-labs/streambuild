"""Stable authentication and account-control constants."""

from uuid import NAMESPACE_URL, UUID, uuid5

ADMIN_ROLE: str = "admin"
VIEWER_ROLE: str = "viewer"
ACCOUNT_SCHEMA_COMPONENT: str = "accounts"
CSRF_HEADER: str = "X-StreamBuild-CSRF"
TRUSTED_PROXY_CSRF_PROOF: str = "trusted-proxy"
PASSWORD_MIN_LENGTH: int = 12
LOGIN_ATTEMPT_WINDOW_MINUTES: int = 1
LOGIN_USER_ATTEMPT_LIMIT: int = 5
LOGIN_IP_ATTEMPT_LIMIT: int = 20
LOGIN_LIMITER_MAX_KEYS: int = 2048
SQLITE_MEMORY_PATH: str = ":memory:"
SQLITE_MEMORY_URLS: frozenset[str] = frozenset({"sqlite://", "sqlite:///:memory:"})
LOCALHOST_NAME: str = "localhost"
LOCAL_USER_ID: UUID = uuid5(NAMESPACE_URL, "https://streambuild.dev/principals/local")
PUBLIC_API_PATHS: frozenset[str] = frozenset({"/api/auth/config", "/api/auth/login"})
UNSAFE_HTTP_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
