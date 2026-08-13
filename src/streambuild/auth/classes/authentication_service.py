"""Authentication mechanism dispatch and principal resolution."""

from __future__ import annotations

import hmac
from collections.abc import Mapping

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


class AuthenticationService:
    """Resolve every configured mechanism into one principal contract."""

    def __init__(self, *, settings: AuthSettings, store: ControlStore) -> None:
        self.settings = settings
        self.store = store

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

    def roles_for(self, *, principal: Principal) -> tuple[str, ...]:
        if principal.authentication_source == AuthenticationSource.LOCAL:
            return (ADMIN_ROLE,)
        account: UserAccount | None = self.store.get_user_by_id(user_id=principal.user_id)
        if account is None or not account.is_active:
            raise AuthorizationError("Account is disabled or no longer exists")
        return account.roles

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
        return AuthenticatedRequest(
            principal=_principal(account=account, source=AuthenticationSource.TRUSTED_PROXY),
            roles=account.roles,
        )

    def _authenticate_session(self, *, cookies: Mapping[str, str]) -> AuthenticatedRequest:
        token: str | None = cookies.get(self.settings.session_cookie_name)
        if token is None:
            raise AuthenticationError("Authentication required")
        resolved: ResolvedSession | None = self.store.resolve_session(token=token)
        if resolved is None:
            raise AuthenticationError("Session is invalid or expired")
        return AuthenticatedRequest(
            principal=resolved.principal,
            roles=self.roles_for(principal=resolved.principal),
            csrf_token=resolved.csrf_token,
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
