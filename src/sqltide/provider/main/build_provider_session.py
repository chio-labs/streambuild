"""Apache-2.0: SQLBuild provider/main/session.py@7625d22e2716."""

from __future__ import annotations

from sqltide.provider.classes.session import ProviderSession
from sqltide.provider.models import DiscoveredProvider
from sqltide.providers import Provider


def build_provider_session(
    *,
    discovered_providers: tuple[DiscoveredProvider, ...],
    setup_context: object | None = None,
) -> ProviderSession:
    """Build a runtime provider session with fresh provider instances."""

    providers: dict[str, Provider] = {
        discovered_provider.name: discovered_provider.provider_class()
        for discovered_provider in discovered_providers
    }
    return ProviderSession(providers, setup_context=setup_context)
