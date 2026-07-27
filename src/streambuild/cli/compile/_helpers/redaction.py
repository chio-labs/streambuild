"""Redact source credentials from deterministic static compile products."""

from dataclasses import replace

from streambuild.adapter.constants import REDACTED_SECRET_PLACEHOLDER
from streambuild.adapter.models import AdapterManagedSource
from streambuild.cli.compile.constants import (
    BROKER_USERINFO_SEPARATOR,
    SENSITIVE_SOURCE_SETTING_FRAGMENTS,
)


def redacted_managed_source(resource: AdapterManagedSource) -> AdapterManagedSource:
    """Return a static-artifact copy with credential-bearing values removed."""

    broker_list: str = (
        REDACTED_SECRET_PLACEHOLDER
        if BROKER_USERINFO_SEPARATOR in resource.broker_list
        else resource.broker_list
    )
    settings: tuple[tuple[str, str], ...] = _redacted_settings(resource.settings)
    return replace(resource, broker_list=broker_list, settings=settings)


def _redacted_settings(settings: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    redacted: list[tuple[str, str]] = []
    key: str
    value: str
    for key, value in settings:
        rendered_value: str = REDACTED_SECRET_PLACEHOLDER if _is_sensitive_key(key) else value
        redacted.append((key, rendered_value))
    return tuple(redacted)


def _is_sensitive_key(key: str) -> bool:
    lowered_key: str = key.lower()
    return any(fragment in lowered_key for fragment in SENSITIVE_SOURCE_SETTING_FRAGMENTS)
