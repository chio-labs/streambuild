"""Authentication mechanism dispatch and principal resolution."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from threading import Lock

from streambuild.auth._helpers.usernames import canonical_username
from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.constants import ADMIN_ROLE, LOCAL_USER_ID, TRUSTED_PROXY_CSRF_PROOF
from streambuild.auth.exceptions import AuthenticationError, AuthorizationError
from streambuild.auth.models import (
    AuthenticatedRequest,
    AuthSettings,
    Principal,
    ResolvedSession,
    UserAccount,
)
from streambuild.auth.types import AuthenticationMode, AuthenticationSource, UnknownUserPolicy

_AUTHENTICATION_CACHE_TTL_SECONDS: float = 5.0
_AUTHENTICATION_CACHE_MAX_ENTRIES: int = 1024


class AuthenticationService:
    """Resolve every configured mechanism into one principal contract."""

    def __init__(self, *, settings: AuthSettings, store: ControlStore) -> None:
        self.settings = settings
        self.store = store
        self._cache: dict[str, tuple[float, int, AuthenticatedRequest]] = {}
        self._cache_lock: Lock = Lock()

    def authenticate(
        self,
        *,
        headers: Mapping[str, str],
        cookies: Mapping[str, str],
    ) -> AuthenticatedRequest:
        if self.settings.mode == AuthenticationMode.DISABLED:
            return AuthenticatedRequest(
                principal=Principal(
                    user_id=LOCAL_USER_ID,
                    username="local",
                    display_name="Local developer",
                    email=None,
                    authentication_source=AuthenticationSource.LOCAL,
                ),
                roles=(ADMIN_ROLE,),
            )
        if self.settings.mode == AuthenticationMode.TRUSTED_PROXY:
            return self._authenticate_proxy(headers=headers)
        return self._authenticate_session(cookies=cookies)

    def require_csrf(
        self,
        *,
        authenticated: AuthenticatedRequest,
        supplied_token: str | None,
    ) -> None:
        source: AuthenticationSource = authenticated.principal.authentication_source
        if source == AuthenticationSource.LOCAL:
            return
        if source == AuthenticationSource.TRUSTED_PROXY:
            if supplied_token != TRUSTED_PROXY_CSRF_PROOF:
                raise AuthorizationError("Missing trusted-proxy request proof")
            return
        expected: str | None = authenticated.csrf_token
        if (
            expected is None
            or supplied_token is None
            or not hmac.compare_digest(expected, supplied_token)
        ):
            raise AuthorizationError("Missing or invalid CSRF token")

    def _authenticate_proxy(self, *, headers: Mapping[str, str]) -> AuthenticatedRequest:
        raw_username: str | None = headers.get(self.settings.username_header)
        if raw_username is None or not raw_username.strip():
            raise AuthenticationError(
                f"Trusted proxy did not provide required header '{self.settings.username_header}'"
            )
        try:
            username: str = canonical_username(raw_username)
        except ValueError as error:
            raise AuthenticationError(str(error)) from error
        subject: str = username
        cache_key: str = f"proxy:{subject}"
        cached: AuthenticatedRequest | None = self._cached(cache_key=cache_key)
        if cached is not None:
            return cached
        account: UserAccount | None = self.store.resolve_external_identity(
            source=AuthenticationSource.TRUSTED_PROXY,
            subject=subject,
        )
        if account is None:
            if self.settings.unknown_user_policy == UnknownUserPolicy.DENY:
                raise AuthorizationError(
                    f"Authenticated proxy user '{username}' is not provisioned in StreamBuild"
                )
            account = self.store.provision_proxy_user(
                subject=subject,
                username=username,
                display_name=_optional_header(
                    headers=headers, name=self.settings.display_name_header
                ),
                email=_optional_header(headers=headers, name=self.settings.email_header),
                default_role=self.settings.default_role,
            )
        if not account.is_active:
            raise AuthorizationError("Account is disabled")
        authenticated: AuthenticatedRequest = AuthenticatedRequest(
            principal=_principal(account=account, source=AuthenticationSource.TRUSTED_PROXY),
            roles=account.roles,
        )
        self._remember(cache_key=cache_key, authenticated=authenticated)
        return authenticated

    def _authenticate_session(self, *, cookies: Mapping[str, str]) -> AuthenticatedRequest:
        token: str | None = cookies.get(self.settings.session_cookie_name)
        if token is None:
            raise AuthenticationError("Authentication required")
        cache_key: str = f"session:{hashlib.sha256(token.encode()).hexdigest()}"
        cached: AuthenticatedRequest | None = self._cached(cache_key=cache_key)
        if cached is not None:
            return cached
        resolved: ResolvedSession | None = self.store.resolve_session(token=token)
        if resolved is None:
            raise AuthenticationError("Session is invalid or expired")
        authenticated: AuthenticatedRequest = AuthenticatedRequest(
            principal=resolved.principal,
            roles=resolved.roles,
            csrf_token=resolved.csrf_token,
        )
        self._remember(cache_key=cache_key, authenticated=authenticated)
        return authenticated

    def _cached(self, *, cache_key: str) -> AuthenticatedRequest | None:
        now: float = time.monotonic()
        revision: int = self.store.authentication_revision
        with self._cache_lock:
            cached: tuple[float, int, AuthenticatedRequest] | None = self._cache.get(cache_key)
            if cached is None:
                return None
            expires_at, cached_revision, authenticated = cached
            if expires_at <= now or cached_revision != revision:
                self._cache.pop(cache_key, None)
                return None
            return authenticated

    def _remember(self, *, cache_key: str, authenticated: AuthenticatedRequest) -> None:
        now: float = time.monotonic()
        with self._cache_lock:
            if len(self._cache) >= _AUTHENTICATION_CACHE_MAX_ENTRIES:
                self._cache = {key: value for key, value in self._cache.items() if value[0] > now}
            self._cache[cache_key] = (
                now + _AUTHENTICATION_CACHE_TTL_SECONDS,
                self.store.authentication_revision,
                authenticated,
            )


def _optional_header(*, headers: Mapping[str, str], name: str | None) -> str | None:
    if name is None:
        return None
    value: str | None = headers.get(name)
    if value is None:
        return None
    cleaned: str = value.strip()
    return cleaned or None


def _principal(*, account: UserAccount, source: AuthenticationSource) -> Principal:
    return Principal(
        user_id=account.user_id,
        username=account.username,
        display_name=account.display_name,
        email=account.email,
        authentication_source=source,
    )
