"""Redact credential-bearing source values before they leave the process."""

from __future__ import annotations

from collections.abc import Mapping

from streambuild.dev_server.constants import (
    BROKER_USERINFO_SEPARATOR,
    REDACTED_SECRET_PLACEHOLDER,
    SENSITIVE_SOURCE_SETTING_FRAGMENTS,
)


def redacted_broker_list(broker_list: str) -> str:
    """Hide the whole value when it can carry userinfo credentials."""

    if BROKER_USERINFO_SEPARATOR in broker_list:
        return REDACTED_SECRET_PLACEHOLDER
    return broker_list


def redacted_source_settings(settings: Mapping[str, str] | None) -> dict[str, str] | None:
    """Replace values of credential-bearing setting keys."""

    if settings is None:
        return None
    redacted: dict[str, str] = {}
    key: str
    value: str
    for key, value in settings.items():
        redacted[key] = REDACTED_SECRET_PLACEHOLDER if _is_sensitive_key(key) else value
    return redacted


def _is_sensitive_key(key: str) -> bool:
    lowered: str = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_SOURCE_SETTING_FRAGMENTS)
